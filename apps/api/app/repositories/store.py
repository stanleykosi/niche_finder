"""Transaction-oriented repositories for the MVP control plane."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..db.models import (
    BrowserMediaObservation,
    Channel,
    ChannelSnapshot,
    CommentSample,
    EvidenceRecord,
    FormatCluster,
    NicheCandidate,
    OutlierResult,
    ResearchRun,
    RuntimeArtifact,
    SearchObservation,
    SourceRoutingAudit,
    TaskJob,
    Video,
    VideoSnapshot,
    ViralMechanismAnalysis,
    WinnerLoserComparison,
    new_id,
    utc_now,
)
from ..domain.contracts import ResearchRunCreate


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, request: ResearchRunCreate) -> ResearchRun:
        run = ResearchRun(
            id=new_id(),
            status="queued",
            requested_format=request.requested_format.value,
            language=request.language,
            regions=request.regions,
            seeds=request.seeds,
            recency_config={"days": request.recency_days},
            research_limits=request.limits.model_dump(mode="json"),
            configuration=request.model_dump(mode="json"),
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, run_id: str | UUID) -> ResearchRun | None:
        return self.session.get(ResearchRun, str(run_id))

    def cancel_run_if_active(self, run_id: str | UUID, reason: str) -> tuple[ResearchRun, bool]:
        """Atomically cancel only a run that has not reached a worker-owned terminal state."""
        normalized_id = str(run_id)
        result = self.session.execute(
            update(ResearchRun)
            .where(
                ResearchRun.id == normalized_id,
                ResearchRun.status.in_({"queued", "planning", "discovering", "enriching", "analysing", "reporting"}),
            )
            .values(status="cancelled", completed_at=utc_now(), failure_reason=reason)
        )
        self.session.commit()
        self.session.expire_all()
        run = self.get_run(normalized_id)
        if run is None:
            raise KeyError(normalized_id)
        return run, bool(result.rowcount)

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[ResearchRun]:
        return list(self.session.scalars(
            select(ResearchRun)
            .order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc())
            .offset(offset)
            .limit(limit)
        ))

    def count_runs(self) -> int:
        return int(self.session.scalar(select(func.count(ResearchRun.id))) or 0)

    def prepare_run_for_resume(self, run_id: str | UUID) -> ResearchRun:
        """Reset only derived relational output while preserving durable evidence.

        Discovery observations, per-video enrichment, browser/media observations,
        evidence, and pipeline checkpoints are the expensive durable work of a
        run.  They must survive a worker restart.  Derived rows are cheap to
        rebuild and may be internally inconsistent when execution stopped in the
        middle of analysis, so those rows alone are replaced on resume.
        """
        normalized_id = str(run_id)
        run = self.get_run(normalized_id)
        if run is None:
            raise KeyError(normalized_id)
        cluster_ids = list(self.session.scalars(
            select(FormatCluster.id).where(FormatCluster.research_run_id == normalized_id)
        ))
        if cluster_ids:
            self.session.execute(delete(ViralMechanismAnalysis).where(
                ViralMechanismAnalysis.format_cluster_id.in_(cluster_ids)
            ))
        for model in (
            NicheCandidate,
            WinnerLoserComparison,
            OutlierResult,
            FormatCluster,
        ):
            self.session.execute(delete(model).where(model.research_run_id == normalized_id))
        run.status = "queued"
        run.completed_at = None
        run.failure_reason = None
        self.session.commit()
        return run

    def reset_run_outputs_for_retry(self, run_id: str | UUID) -> ResearchRun:
        """Backward-compatible alias for checkpoint-preserving resume."""
        return self.prepare_run_for_resume(run_id)

    def recoverable_runs(self) -> list[ResearchRun]:
        return list(self.session.scalars(
            select(ResearchRun)
            .where(ResearchRun.status.in_({"queued", "planning", "discovering", "enriching", "analysing", "reporting"}))
            .order_by(ResearchRun.created_at, ResearchRun.id)
        ))

    def transition(self, run: ResearchRun, status: str, failure_reason: str | None = None) -> None:
        run.status = status
        if status == "planning" and run.started_at is None:
            run.started_at = utc_now()
        if status in {"complete", "failed", "cancelled"}:
            run.completed_at = utc_now()
        if failure_reason:
            run.failure_reason = failure_reason
        self.session.commit()

    def add_search_observation(self, run_id: str, payload: dict[str, Any]) -> SearchObservation:
        item = SearchObservation(research_run_id=run_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def upsert_channel(self, record: Any, source: str = "fixture_api", run_id: str | UUID | None = None) -> Channel:
        _insert_ignore(self.session, Channel, {
            "id": new_id(), "youtube_channel_id": record.youtube_channel_id,
            "canonical_url": record.canonical_url, "title": record.title,
            "description": record.description,
        }, ["youtube_channel_id"])
        channel = self.session.scalar(select(Channel).where(Channel.youtube_channel_id == record.youtube_channel_id))
        if channel is None:  # pragma: no cover - database invariant defense
            raise RuntimeError("atomic channel upsert did not return the shared entity")
        # A keyless video response may only know the channel ID and synthesize
        # the default /channel/{id} URL. Those placeholders cannot erase a
        # previously authoritative channel title or canonical handle URL.
        if _authoritative_channel_url(record, source) or not channel.canonical_url:
            channel.canonical_url = record.canonical_url
        if _authoritative_channel_title(record, source) or not channel.title:
            channel.title = record.title
        # Empty keyless/video-level metadata must not erase a description
        # previously observed from a channel-level API response.
        if record.description and record.description.strip():
            channel.description = record.description
        snapshot = None
        if run_id is not None:
            snapshot = self.session.scalar(select(ChannelSnapshot).where(
                ChannelSnapshot.research_run_id == str(run_id),
                ChannelSnapshot.channel_id == channel.id,
                ChannelSnapshot.source == source,
            ))
        if snapshot is None and run_id is not None:
            _insert_ignore(self.session, ChannelSnapshot, {
                "id": new_id(), "research_run_id": str(run_id), "channel_id": channel.id,
                "subscriber_count": record.subscriber_count, "total_view_count": record.total_view_count,
                "video_count": record.video_count, "source": source,
            }, ["research_run_id", "channel_id", "source"])
            snapshot = self.session.scalar(select(ChannelSnapshot).where(
                ChannelSnapshot.research_run_id == str(run_id),
                ChannelSnapshot.channel_id == channel.id,
                ChannelSnapshot.source == source,
            ))
        elif snapshot is None:
            snapshot = ChannelSnapshot(
                research_run_id=None, channel_id=channel.id,
                subscriber_count=record.subscriber_count, total_view_count=record.total_view_count,
                video_count=record.video_count, source=source,
            )
            self.session.add(snapshot)
        else:
            snapshot.observed_at = utc_now()
            snapshot.subscriber_count = record.subscriber_count
            snapshot.total_view_count = record.total_view_count
            snapshot.video_count = record.video_count
        self.session.commit()
        return channel

    def upsert_video(self, record: Any, channel: Channel | None, source: str = "fixture_api", run_id: str | UUID | None = None) -> Video:
        _insert_ignore(self.session, Video, {
            "id": new_id(), "youtube_video_id": record.youtube_video_id,
            "channel_id": channel.id if channel else None, "canonical_url": record.canonical_url,
            "title": record.title, "description": record.description,
            "duration_seconds": record.duration_seconds, "published_at": record.published_at,
            "category_id": record.category_id, "tags": record.tags, "thumbnails": record.thumbnails,
        }, ["youtube_video_id"])
        video = self.session.scalar(select(Video).where(Video.youtube_video_id == record.youtube_video_id))
        if video is None:  # pragma: no cover - database invariant defense
            raise RuntimeError("atomic video upsert did not return the shared entity")
        # Later authoritative enrichment refreshes every normalized field,
        # while empty sparse values cannot erase previously known data.
        if record.canonical_url and record.canonical_url.strip():
            video.canonical_url = record.canonical_url
        if record.title and record.title.strip():
            video.title = record.title
        if record.description and record.description.strip():
            video.description = record.description
        if record.duration_seconds is not None and record.duration_seconds > 0:
            video.duration_seconds = record.duration_seconds
        video.published_at = record.published_at
        if record.category_id and record.category_id.strip():
            video.category_id = record.category_id
        if record.tags:
            video.tags = record.tags
        if record.thumbnails:
            video.thumbnails = record.thumbnails
        if channel is not None:
            video.channel_id = channel.id
        video.updated_at = utc_now()
        snapshot = None
        if run_id is not None:
            snapshot = self.session.scalar(select(VideoSnapshot).where(
                VideoSnapshot.research_run_id == str(run_id),
                VideoSnapshot.video_id == video.id,
                VideoSnapshot.source == source,
            ))
        if snapshot is None and run_id is not None:
            _insert_ignore(self.session, VideoSnapshot, {
                "id": new_id(), "research_run_id": str(run_id), "video_id": video.id,
                "view_count": record.view_count, "like_count": record.like_count,
                "comment_count": record.comment_count, "source": source,
            }, ["research_run_id", "video_id", "source"])
            snapshot = self.session.scalar(select(VideoSnapshot).where(
                VideoSnapshot.research_run_id == str(run_id),
                VideoSnapshot.video_id == video.id,
                VideoSnapshot.source == source,
            ))
        elif snapshot is None:
            snapshot = VideoSnapshot(
                research_run_id=None, video_id=video.id, view_count=record.view_count,
                like_count=record.like_count, comment_count=record.comment_count, source=source,
            )
            self.session.add(snapshot)
        else:
            snapshot.observed_at = utc_now()
            snapshot.view_count = record.view_count
            snapshot.like_count = record.like_count
            snapshot.comment_count = record.comment_count
        self.session.commit()
        return video

    def add_comment_samples(self, video_id: str, comments: Iterable[Any], source: str) -> None:
        for record in comments:
            _insert_ignore(self.session, CommentSample, {
                "id": new_id(), "video_id": video_id,
                "source_comment_id": record.source_comment_id, "text": record.text,
                "like_count": record.like_count, "published_at": record.published_at,
                "is_pinned_if_known": record.is_pinned_if_known, "source": source,
            }, ["video_id", "source_comment_id", "source"])
            item = self.session.scalar(select(CommentSample).where(
                CommentSample.video_id == video_id,
                CommentSample.source_comment_id == record.source_comment_id,
                CommentSample.source == source,
            ))
            if item is not None:
                item.text = record.text
                item.like_count = record.like_count
                item.published_at = record.published_at
                item.is_pinned_if_known = record.is_pinned_if_known
                item.observed_at = utc_now()
        self.session.commit()

    def add_browser_media(self, run_id: str, video_id: str, record: Any) -> BrowserMediaObservation:
        item = self.session.scalar(select(BrowserMediaObservation).where(
            BrowserMediaObservation.research_run_id == run_id,
            BrowserMediaObservation.video_id == video_id,
        ).order_by(BrowserMediaObservation.observed_at.desc()))
        if item is None:
            item = BrowserMediaObservation(
                id=new_id(), research_run_id=run_id, video_id=video_id,
                source_profile=record.source_profile,
            )
            self.session.add(item)
        item.source_profile = record.source_profile
        item.is_short_presentation = record.is_short_presentation
        item.visible_transcript = record.visible_transcript
        item.thumbnail_ref = record.thumbnail_ref
        item.frame_refs = record.frame_refs
        item.opening_visual_summary = record.opening_visual_summary
        item.caption_style = record.caption_style
        item.observable_structure = record.observable_structure
        item.observed_at = record.observed_at
        item.feature_payload = {
            "first_spoken_line": record.first_spoken_line, "duration_seconds": record.duration_seconds,
            "scene_change_count": record.scene_change_count, "average_shot_duration_seconds": record.average_shot_duration_seconds,
            "reveal_timestamp_seconds": record.reveal_timestamp_seconds, "caption_density": record.caption_density,
            "motion_score": record.motion_score, "pacing_score": record.pacing_score, "visual_features": record.visual_features,
            "music_cue_count": record.music_cue_count, "editing_pattern": record.editing_pattern,
        }
        item.confidence = record.confidence
        self.session.commit()
        return item

    def add_evidence(self, run_id: str, evidence: dict[str, Any]) -> EvidenceRecord:
        item = EvidenceRecord(id=new_id(), research_run_id=run_id, **evidence)
        self.session.add(item)
        self.session.commit()
        return item

    def upsert_evidence(self, run_id: str, evidence: dict[str, Any]) -> EvidenceRecord:
        """Persist one stable evidence item per run/type/source entity."""
        entity_id = evidence.get("source_entity_id")
        item = self.session.scalar(
            select(EvidenceRecord)
            .where(
                EvidenceRecord.research_run_id == run_id,
                EvidenceRecord.evidence_type == evidence["evidence_type"],
                EvidenceRecord.source_entity_id == entity_id,
            )
            .order_by(EvidenceRecord.observed_at.desc())
        )
        if item is None:
            return self.add_evidence(run_id, evidence)
        for key, value in evidence.items():
            setattr(item, key, value)
        if "observed_at" not in evidence:
            item.observed_at = utc_now()
        self.session.commit()
        return item

    def evidence_item(
        self,
        run_id: str,
        evidence_type: str,
        source_entity_id: str | None,
    ) -> EvidenceRecord | None:
        return self.session.scalar(
            select(EvidenceRecord)
            .where(
                EvidenceRecord.research_run_id == run_id,
                EvidenceRecord.evidence_type == evidence_type,
                EvidenceRecord.source_entity_id == source_entity_id,
            )
            .order_by(EvidenceRecord.observed_at.desc())
        )

    def save_checkpoint(
        self,
        run_id: str,
        checkpoint_key: str,
        state: dict[str, Any],
        summary: str,
    ) -> EvidenceRecord:
        return self.upsert_evidence(run_id, {
            "evidence_type": "pipeline_checkpoint",
            "source_type": "deterministic",
            "source_entity_id": checkpoint_key,
            "payload": {"checkpoint_version": "pipeline-v1", "state": state},
            "confidence": 1.0,
            "human_readable_summary": summary,
        })

    def get_checkpoint(self, run_id: str, checkpoint_key: str) -> dict[str, Any] | None:
        item = self.evidence_item(run_id, "pipeline_checkpoint", checkpoint_key)
        if item is None or item.payload.get("checkpoint_version") != "pipeline-v1":
            return None
        state = item.payload.get("state")
        return state if isinstance(state, dict) else None

    def add_routing_audit(self, run_id: str | None, task_type: str, source: str, reason: str, quota_delta: int = 0) -> None:
        self.session.add(SourceRoutingAudit(
            id=new_id(), research_run_id=run_id, task_type=task_type,
            selected_source=source, reason=reason, quota_delta=quota_delta,
        ))
        self.session.commit()

    def add_cluster(self, run_id: str, payload: dict[str, Any]) -> FormatCluster:
        item = FormatCluster(id=new_id(), research_run_id=run_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def add_outlier(self, run_id: str, video_id: str, payload: dict[str, Any]) -> OutlierResult:
        item = OutlierResult(id=new_id(), research_run_id=run_id, video_id=video_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def add_mechanism(self, cluster_id: str, payload: dict[str, Any]) -> ViralMechanismAnalysis:
        item = ViralMechanismAnalysis(id=new_id(), format_cluster_id=cluster_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def add_comparison(self, run_id: str, payload: dict[str, Any]) -> WinnerLoserComparison:
        item = WinnerLoserComparison(id=new_id(), research_run_id=run_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def add_candidate(self, run_id: str, payload: dict[str, Any]) -> NicheCandidate:
        item = NicheCandidate(id=new_id(), research_run_id=run_id, **payload)
        self.session.add(item)
        self.session.commit()
        return item

    def get_candidates(self, run_id: str) -> list[NicheCandidate]:
        return list(self.session.scalars(select(NicheCandidate).where(NicheCandidate.research_run_id == run_id).order_by(NicheCandidate.rank)))

    def get_evidence(self, run_id: str, *, include_checkpoints: bool = False) -> list[EvidenceRecord]:
        query = select(EvidenceRecord).where(EvidenceRecord.research_run_id == run_id)
        if not include_checkpoints:
            query = query.where(EvidenceRecord.evidence_type != "pipeline_checkpoint")
        return list(self.session.scalars(query.order_by(EvidenceRecord.observed_at)))

    def browser_media_rows(self, run_id: str) -> list[tuple[BrowserMediaObservation, str]]:
        return list(self.session.execute(
            select(BrowserMediaObservation, Video.youtube_video_id)
            .join(Video, Video.id == BrowserMediaObservation.video_id)
            .where(BrowserMediaObservation.research_run_id == run_id)
            .order_by(BrowserMediaObservation.observed_at)
        ).all())

    def video_rows_for_run(self, run_id: str) -> list[tuple[Video, VideoSnapshot, Channel | None]]:
        return list(self.session.execute(
            select(Video, VideoSnapshot, Channel)
            .join(VideoSnapshot, VideoSnapshot.video_id == Video.id)
            .outerjoin(Channel, Channel.id == Video.channel_id)
            .where(VideoSnapshot.research_run_id == run_id)
            .order_by(VideoSnapshot.observed_at, Video.youtube_video_id)
        ).all())

    def get_observations(self, run_id: str) -> list[SearchObservation]:
        return list(self.session.scalars(select(SearchObservation).where(SearchObservation.research_run_id == run_id).order_by(SearchObservation.result_position)))

    def get_videos_for_run(self, run_id: str) -> list[Video]:
        query = select(Video).join(SearchObservation, SearchObservation.observed_url.like("%" + Video.youtube_video_id + "%")).where(SearchObservation.research_run_id == run_id)
        return list(self.session.scalars(query).unique())

    def video_snapshot_history(self, youtube_video_id: str) -> list[tuple[datetime, int]]:
        video = self.session.scalar(select(Video).where(Video.youtube_video_id == youtube_video_id))
        if video is None:
            return []
        rows = self.session.scalars(select(VideoSnapshot).where(VideoSnapshot.video_id == video.id).order_by(VideoSnapshot.observed_at)).all()
        return [(row.observed_at, row.view_count) for row in rows]

    def upsert_runtime_artifact(self, payload: dict[str, Any]) -> RuntimeArtifact:
        item = self.session.scalar(select(RuntimeArtifact).where(RuntimeArtifact.path == payload["path"]))
        if item is None:
            item = RuntimeArtifact(id=new_id(), **payload)
            self.session.add(item)
        else:
            for key, value in payload.items():
                setattr(item, key, value)
        self.session.commit()
        return item

    def mark_runtime_artifact_deleted(self, path: str, deleted_at: datetime) -> None:
        item = self.session.scalar(select(RuntimeArtifact).where(RuntimeArtifact.path == path))
        if item is not None:
            item.state = "deleted"
            item.deleted_at = deleted_at
            self.session.commit()

    def runtime_artifacts(self, run_id: str | None = None, available_only: bool = False) -> list[RuntimeArtifact]:
        query = select(RuntimeArtifact)
        if run_id is not None:
            query = query.where(RuntimeArtifact.research_run_id == run_id)
        if available_only:
            query = query.where(RuntimeArtifact.state == "available")
        return list(self.session.scalars(query.order_by(RuntimeArtifact.created_at)))

    def ensure_task_job(self, run_id: str, stage: str = "research") -> TaskJob:
        item = self.session.scalar(select(TaskJob).where(TaskJob.research_run_id == run_id, TaskJob.stage == stage))
        if item is None:
            item = TaskJob(id=new_id(), research_run_id=run_id, stage=stage, status="queued")
            self.session.add(item)
            self.session.commit()
        return item

    def task_job(self, run_id: str, stage: str = "research") -> TaskJob | None:
        return self.session.scalar(select(TaskJob).where(
            TaskJob.research_run_id == run_id,
            TaskJob.stage == stage,
        ))

    def update_task_job(self, run_id: str, status: str, error: str | None = None, increment_attempt: bool = False) -> None:
        item = self.ensure_task_job(run_id)
        item.status = status
        item.error = error
        if increment_attempt:
            item.attempts += 1
        self.session.commit()


def _authoritative_channel_title(record: Any, source: str) -> bool:
    title = str(record.title or "").strip()
    if not title or title == str(record.youtube_channel_id):
        return False
    if title.lower() in {"unknown", "unknown channel", "untitled channel"}:
        return False
    return source not in {"browser"} or bool(title)


def _authoritative_channel_url(record: Any, source: str) -> bool:
    url = str(record.canonical_url or "").strip().rstrip("/")
    if not url:
        return False
    channel_id = str(record.youtube_channel_id)
    default_urls = {
        f"https://youtube.com/channel/{channel_id}",
        f"https://www.youtube.com/channel/{channel_id}",
    }
    if source in {"keyless_ytdlp", "browser"} and url in default_urls:
        return False
    return True


def _insert_ignore(
    session: Session,
    model: Any,
    values: dict[str, Any],
    conflict_columns: list[str],
) -> None:
    """Issue one database-native insert that is safe across worker processes."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(model).values(**values).on_conflict_do_nothing(
            index_elements=conflict_columns
        )
    elif dialect == "sqlite":
        statement = sqlite_insert(model).values(**values).on_conflict_do_nothing(
            index_elements=conflict_columns
        )
    else:  # The canonical deployment supports PostgreSQL; SQLite is the closed-test parity database.
        raise RuntimeError(f"atomic upsert is unsupported for SQL dialect {dialect!r}")
    session.execute(statement)

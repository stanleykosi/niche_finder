import Link from 'next/link';
import { ActivityIcon, CompassIcon, ShieldIcon } from './Icon';

export function Shell({ children }: { children: React.ReactNode }) {
  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/" className="brand"><span className="brand-mark"><CompassIcon width={21} height={21}/></span><span>Niche<br/><em>Intel</em></span></Link>
      <div className="side-kicker">Research console</div>
      <nav className="nav" aria-label="Primary navigation">
        <Link href="/" className="nav-link active"><ActivityIcon width={17} height={17}/> Research runs</Link>
        <Link href="/research/new" className="nav-link"><span className="nav-plus">+</span> New research</Link>
      </nav>
      <div className="sidebar-foot"><ShieldIcon width={17} height={17}/><span>Evidence stays<br/>attached to every claim.</span></div>
    </aside>
    <main className="main-content">{children}</main>
  </div>;
}


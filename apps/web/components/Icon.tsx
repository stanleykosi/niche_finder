import type { SVGProps } from 'react';

export function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: React.ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{children}</svg>;
}
export const CompassIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><circle cx="12" cy="12" r="8.5"/><path d="m14.9 9.1-1.8 4-4 1.8 1.8-4z"/></Icon>;
export const PlusIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 5v14M5 12h14"/></Icon>;
export const ArrowIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M5 12h13M13 6l6 6-6 6"/></Icon>;
export const ActivityIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M4 12h3l2-6 4 12 2-6h5"/></Icon>;
export const ShieldIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 3 19 6v5c0 4.6-3 8-7 10-4-2-7-5.4-7-10V6z"/><path d="m9 12 2 2 4-4"/></Icon>;
export const ChartIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M5 19V9M12 19V5M19 19v-7"/></Icon>;


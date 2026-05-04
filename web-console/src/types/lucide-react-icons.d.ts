declare module 'lucide-react/dist/esm/icons/*.js' {
  import type { ForwardRefExoticComponent, RefAttributes, SVGProps } from 'react';

  const Icon: ForwardRefExoticComponent<Omit<SVGProps<SVGSVGElement>, 'ref'> & RefAttributes<SVGSVGElement>>;
  export default Icon;
}

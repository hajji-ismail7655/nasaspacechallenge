import { ICON } from '../data.js';
export default function Icon({ k }) {
  return <svg className="i" viewBox="0 0 24 24" dangerouslySetInnerHTML={{ __html: ICON[k] }} />;
}

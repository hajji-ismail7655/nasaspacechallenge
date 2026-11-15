const I = {
  roll: <><circle cx="12" cy="12" r="8" /><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16" /></>,
  pan: <path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3" />,
  pointer: <><circle cx="12" cy="12" r="3" /><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /></>,
  area: <><rect x="5" y="5" width="14" height="14" strokeDasharray="3 3" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  reset: <path d="M4 12a8 8 0 1 0 3-6.2M4 4v4h4" />,
};
const Icon = ({ n }) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">{I[n]}</svg>;

const Btn = ({ icon, label, on, onClick, toggle = true }) => (
  <button className={`tool${on ? ' is-on' : ''}`} aria-pressed={toggle ? !!on : undefined} onClick={onClick}>
    <Icon n={icon} /><span>{label}</span>
  </button>
);

/* mode: '3d' | '2d'. Roll (3d) and Pan (2d) are the "move" tool; it excludes Area because both use dragging. */
export default function Toolbar({ mode, tools, onToggle, onZoom, onReset }) {
  const move = mode === '3d' ? 'roll' : 'pan';
  return (
    <div className="toolbar" role="toolbar" aria-label="Tools">
      <Btn icon={move} label={mode === '3d' ? 'Roll' : 'Move'} on={tools[move]} onClick={() => onToggle(move)} />
      <i className="toolbar__sep" />
      <Btn icon="pointer" label="Pointer" on={tools.pointer} onClick={() => onToggle('pointer')} />
      <Btn icon="area" label="Area" on={tools.area} onClick={() => onToggle('area')} />
      <i className="toolbar__sep" />
      <Btn icon="minus" label="Zoom out" toggle={false} onClick={() => onZoom(1 / 1.4)} />
      <Btn icon="plus" label="Zoom in" toggle={false} onClick={() => onZoom(1.4)} />
      <Btn icon="reset" label="Reset view" toggle={false} onClick={onReset} />
    </div>
  );
}

const I = {
  roll: <><circle cx="12" cy="12" r="8" /><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16" /></>,
  pan: <path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3" />,
  pointer: <><circle cx="12" cy="12" r="3" /><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /></>,
  area: <><rect x="5" y="5" width="14" height="14" strokeDasharray="3 3" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  sliders: <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6" />,
  reset: <path d="M4 12a8 8 0 1 0 3-6.2M4 4v4h4" />,
};
const Icon = ({ n }) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">{I[n]}</svg>;

const Btn = ({ icon, label, on, onClick, toggle = true }) => (
  <button className={`tool${on ? ' is-on' : ''}`} aria-pressed={toggle ? !!on : undefined} onClick={onClick}>
    <Icon n={icon} /><span>{label}</span>
  </button>
);

/* Movement is always free (drag to roll/move; right-drag or Shift-drag while Area is on; arrow keys on the globe). */
export default function Toolbar({ tools, onToggle, onZoom, onReset, weightsOn, onWeights }) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Tools">
      <Btn icon="pointer" label="Pointer" on={tools.pointer} onClick={() => onToggle('pointer')} />
      <Btn icon="area" label="Area" on={tools.area} onClick={() => onToggle('area')} />
      <Btn icon="sliders" label="Weights" on={weightsOn} onClick={onWeights} />
      <i className="toolbar__sep" />
      <Btn icon="minus" label="Zoom out" toggle={false} onClick={() => onZoom(1 / 1.4)} />
      <Btn icon="plus" label="Zoom in" toggle={false} onClick={() => onZoom(1.4)} />
      <Btn icon="reset" label="Reset view" toggle={false} onClick={onReset} />
    </div>
  );
}

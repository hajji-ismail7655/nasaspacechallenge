export default function Dock({ targets, selected, onSelect, onRun }) {
  const group = (title, id, body) => (
    <div className="grp"><b>{title}</b>
      <div className="chips" id={id}>
        {targets.filter(t => t.body === body).map(t =>
          <button key={t.id} className={'chip' + (selected && selected.id === t.id ? ' on' : '')} onClick={() => onSelect(t)}>{t.name}</button>)}
      </div>
    </div>);
  return (
    <div className="dock">
      {group('MOON TARGETS', 'cm', 'moon')}{group('MARS TARGETS', 'cr', 'mars')}
      <button id="run" disabled={!selected} onClick={() => selected && onRun(selected)}>Run analysis</button>
    </div>);
}

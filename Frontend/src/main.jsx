import { createRoot } from 'react-dom/client';
import './styles.css';
import App from './App.jsx';

// No <StrictMode>: boot() builds one WebGL context and audio players, which must not be created twice in dev.
createRoot(document.getElementById('root')).render(<App />);

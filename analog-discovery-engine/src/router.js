import { useEffect, useState } from 'react';

const read = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);

export const navigate = (to) => {
  location.hash = '#/' + String(to).replace(/^\/+/, '');
};

export function useRoute() {
  const [segments, setSegments] = useState(read);
  useEffect(() => {
    const on = () => setSegments(read());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return segments;
}

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createTransport } from './api';
import { App } from './App';
import './styles.css';

const root = createRoot(document.getElementById('root') as HTMLElement);

void createTransport().then((transport) => {
  root.render(
    <StrictMode>
      <App transport={transport} />
    </StrictMode>,
  );
});

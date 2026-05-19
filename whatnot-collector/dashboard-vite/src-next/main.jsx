import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './ops-next.css';
import OpsNextApp from './OpsNextApp.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <OpsNextApp />
    </BrowserRouter>
  </StrictMode>,
);

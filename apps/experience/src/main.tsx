/**
 * Experience participant entry: hash route `#/play/<token>`.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MotionConfig } from 'motion/react';
import '../../../packages/ui/tokens.css';
import './styles.css';

import { PlayerPage } from './pages/player.tsx';

function App() {
  return (
    <MotionConfig reducedMotion="user">
      <PlayerPage />
    </MotionConfig>
  );
}

const container = document.getElementById('root');
if (container) createRoot(container).render(<App />);

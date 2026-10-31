/**
 * Shared chrome: brand, backend capability banner and navigation.
 *
 * The model banner is not decoration: a simulated provider must be visible on
 * every screen so nobody reads scripted output as a real generation.
 */
import React, { useEffect, useState } from 'react';

import { client } from '../hooks/use-workbench.ts';
import { Seal, StatusPill } from './primitives.tsx';

export interface Health {
  simulated: boolean;
  provider: string;
  configured: boolean;
  validator: boolean;
}

export function AppShell({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    client
      .health()
      .then((report) =>
        setHealth({
          simulated: report.simulated,
          provider: report.model_provider,
          configured: report.model_configured,
          validator: report.validator_available,
        }),
      )
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Seal filled>叙境</Seal>
          <div>
            <h1>叙境</h1>
            <p>文化资料 · 多 Agent 共创 · 有出处</p>
          </div>
        </div>
        <div className="health">
          {health ? (
            <>
              <StatusPill tone={health.simulated ? 'warn' : health.configured ? 'ok' : 'bad'}>
                {health.simulated
                  ? '模拟模型（结果不代表真实生成）'
                  : health.configured
                    ? `真实模型 · ${health.provider}`
                    : '模型未配置'}
              </StatusPill>
              <StatusPill tone={health.validator ? 'ok' : 'bad'}>
                {health.validator ? '程序检查可用' : '程序检查缺失'}
              </StatusPill>
            </>
          ) : (
            <StatusPill tone="bad">后端未连接</StatusPill>
          )}
        </div>
        {actions}
      </header>
      {children}
    </div>
  );
}

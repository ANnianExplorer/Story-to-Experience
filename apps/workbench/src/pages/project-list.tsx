/**
 * Project list: create a project or open an existing one.
 *
 * Creating a project only records the brief; it never starts a run, so nothing
 * is generated (and nothing is spent) until the creator asks for it.
 */
import React, { useEffect, useState } from 'react';

import type { Project } from '../lib/api.ts';
import { client, type WorkbenchScope } from '../hooks/use-workbench.ts';
import { Field, Panel } from '../components/primitives.tsx';

export function ProjectListPage({ scope, onOpen }: { scope: WorkbenchScope; onOpen: (projectId: string) => void }) {
  const { run } = scope;
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('未命名文化体验');
  const [audience, setAudience] = useState('五年级学生');
  const [minutes, setMinutes] = useState(6);
  const [goals, setGoals] = useState('观察工具用途\n理解工序先后');
  const [loading, setLoading] = useState(true);

  const reload = React.useCallback(async () => {
    setProjects(await client.listProjects());
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const create = () =>
    run(async () => {
      const project = await client.createProject(name, {
        audience,
        duration_minutes: minutes,
        learning_goals: goals.split('\n').map((goal) => goal.trim()).filter(Boolean),
      });
      await reload();
      onOpen(project.id);
    });

  return (
    <main className="page single">
      <Panel title="新建项目" headingId="create-heading">
        <form
          className="create"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <Field label="项目名">
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required />
          </Field>
          <Field label="受众">
            <input value={audience} onChange={(event) => setAudience(event.target.value)} maxLength={120} required />
          </Field>
          <Field label="时长（分钟）">
            <input
              type="number"
              min={1}
              max={30}
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
            />
          </Field>
          <Field label="教学目标（每行一条）">
            <textarea value={goals} rows={3} onChange={(event) => setGoals(event.target.value)} />
          </Field>
          <button type="submit" className="primary">
            创建项目
          </button>
        </form>
      </Panel>

      <Panel title="我的项目" headingId="list-heading">
        {loading && <p className="hint">正在加载…</p>}
        {!loading && projects.length === 0 && <p className="hint">还没有项目。先创建一个，再上传材料。</p>}
        <ul className="versions">
          {projects.map((project) => (
            <li key={project.id}>
              <button className="link" onClick={() => onOpen(project.id)}>
                {project.name}
              </button>
              <span className="meta">
                受众 {project.brief.audience} · {project.brief.duration_minutes} 分钟 · 简报 v{project.brief_revision}
              </span>
              {project.stable_version_id ? (
                <span className="pill pill-ok">稳定版</span>
              ) : (
                <span className="pill pill-neutral">未发布</span>
              )}
            </li>
          ))}
        </ul>
      </Panel>
    </main>
  );
}

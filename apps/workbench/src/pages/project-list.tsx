/**
 * Project list: create a project or open an existing one.
 *
 * Creating a project only records the brief; it never starts a run, so nothing
 * is generated (and nothing is spent) until the creator asks for it.
 */
import React, { useEffect, useMemo, useState } from 'react';

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

  // Stable chapter numerals for the list, so the same project keeps its mark.
  const marks = useMemo(
    () => projects.map((_, index) => String(index + 1).padStart(2, '0')),
    [projects.length],
  );

  return (
    <main className="page">
      <div className="intro">
        <p className="xj-kicker">卷一 · 起稿</p>
        <h2>
          先定下<em>为谁而写</em>，再让agents去找依据。
        </h2>
        <p>
          项目只保存简报：受众、时长与教学目标。真正的资料、事实与出处在下个页面里逐条录入，
          未经你确认的内容不会被写成事实。
        </p>
      </div>

      <Panel title="新建项目" headingId="create-heading" index="零一">
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
          <div className="row">
            <button type="submit" className="primary">
              创建项目
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="我的项目" headingId="list-heading" index="零二">
        {loading && <p className="hint">正在加载…</p>}
        {!loading && projects.length === 0 && <p className="hint">还没有项目。先创建一个，再上传材料。</p>}
        <ul className="project-list">
          {projects.map((project, index) => (
            <li key={project.id}>
              <button className="name" onClick={() => onOpen(project.id)}>
                {project.name}
              </button>
              <span className="pill pill-neutral">{marks[index]}</span>
              <span className="desc">
                受众 {project.brief.audience} · {project.brief.duration_minutes} 分钟 · 简报 v{project.brief_revision} ·{' '}
                {project.stable_version_id ? '已有稳定版' : '尚未发布'}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </main>
  );
}

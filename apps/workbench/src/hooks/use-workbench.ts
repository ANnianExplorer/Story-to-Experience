/**
 * Client wiring for the workbench: one API client and one reducer scope.
 *
 * Pages receive these through the hook instead of importing the client module,
 * so tests can inject a fake transport.
 */
import { useCallback, useReducer } from 'react';

import { ApiError, XujingClient } from '../lib/api.ts';
import { initialState, reduce, type WorkbenchAction, type WorkbenchState } from '../lib/workbench-state.ts';

export const client = new XujingClient();

export interface WorkbenchScope {
  state: WorkbenchState;
  dispatch: React.Dispatch<WorkbenchAction>;
  /** Run an async action and map any failure into a visible error state. */
  run: (task: () => Promise<void>) => Promise<void>;
}

export function useWorkbench(clientImpl: XujingClient = client): WorkbenchScope {
  const [state, dispatch] = useReducer(reduce, initialState);
  const run = useCallback(
    async (task: () => Promise<void>) => {
      try {
        await task();
      } catch (error) {
        if (error instanceof ApiError) {
          dispatch({ type: 'error', code: error.code, message: error.message });
        } else {
          dispatch({ type: 'error', code: 'NETWORK', message: '无法连接后端服务，请确认 API 已启动。' });
        }
      }
    },
    [],
  );
  void clientImpl;
  return { state, dispatch, run };
}

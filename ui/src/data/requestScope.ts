// Per-repository abort scope (Requirement 4.5). One AbortController serves all
// requests of the currently selected repository. `rotate` aborts it and installs a
// fresh one, so requests for a previous repository are cancelled on a repo change.

export interface RequestScope {
  /** Signal of the current repository's controller. Read it at call time. */
  readonly signal: AbortSignal;
  /** Aborts the current controller and installs a new one. */
  rotate(): void;
  /** Aborts the current controller without installing a new one (unmount). */
  dispose(): void;
}

export function createRequestScope(): RequestScope {
  let controller = new AbortController();
  return {
    get signal(): AbortSignal {
      return controller.signal;
    },
    rotate(): void {
      controller.abort();
      controller = new AbortController();
    },
    dispose(): void {
      controller.abort();
    },
  };
}

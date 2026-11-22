import { useRef } from 'react';

/** Holds the value of the latest render so async callbacks read current state. */
export function useLatest<T>(value: T): { readonly current: T } {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

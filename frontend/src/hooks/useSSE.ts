import { useEffect } from 'react';
import type { QueryClient } from '@tanstack/react-query';

export function useSSE(queryClient: QueryClient) {
  useEffect(() => {
    const source = new EventSource('/api/events');

    source.addEventListener('lattice_changed', () => {
      queryClient.invalidateQueries();
    });

    source.addEventListener('error', () => {
      // EventSource auto-reconnects on error
    });

    return () => source.close();
  }, [queryClient]);
}

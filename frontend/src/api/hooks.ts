import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { Fact, EnumsData, TagEntry } from '../types/fact';
import type { GraphData } from '../types/graph';

// Read hooks
export function useFacts(params?: Record<string, string>) {
  return useQuery<Fact[]>({
    queryKey: ['facts', params],
    queryFn: () => api.facts.list(params),
  });
}

export function useFact(code: string | null) {
  return useQuery<Fact>({
    queryKey: ['fact', code],
    queryFn: () => api.facts.get(code!),
    enabled: !!code,
  });
}

export function useGraphData(includeInactive = false) {
  return useQuery<GraphData>({
    queryKey: ['graph', includeInactive],
    queryFn: () => api.graph.data(includeInactive),
  });
}

export function useTags() {
  return useQuery<TagEntry[]>({
    queryKey: ['tags'],
    queryFn: () => api.meta.tags(),
    staleTime: 60_000,
  });
}

export function useEnums() {
  return useQuery<EnumsData>({
    queryKey: ['enums'],
    queryFn: () => api.meta.enums(),
    staleTime: Infinity,
  });
}

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => api.meta.stats(),
  });
}

export function useTypes() {
  return useQuery({
    queryKey: ['types'],
    queryFn: () => api.meta.types(),
    staleTime: Infinity,
  });
}

export function useRoles() {
  return useQuery<Record<string, { name: string; description: string }>>({
    queryKey: ['roles'],
    queryFn: () => api.meta.roles(),
    staleTime: Infinity,
  });
}

export function useRoleContext(roleName: string | null) {
  return useQuery({
    queryKey: ['roleContext', roleName],
    queryFn: () => api.meta.roleContext(roleName!),
    enabled: !!roleName,
    staleTime: 30_000,
  });
}

// Mutation hooks
export function useCreateFact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: any) => api.facts.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['facts'] });
      qc.invalidateQueries({ queryKey: ['graph'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function useUpdateFact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, changes, reason }: { code: string; changes: any; reason: string }) =>
      api.facts.update(code, changes, reason),
    onSuccess: (_data, { code }) => {
      qc.invalidateQueries({ queryKey: ['facts'] });
      qc.invalidateQueries({ queryKey: ['fact', code] });
      qc.invalidateQueries({ queryKey: ['graph'] });
    },
  });
}

export function useDeprecateFact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, reason }: { code: string; reason: string }) =>
      api.facts.deprecate(code, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['facts'] });
      qc.invalidateQueries({ queryKey: ['graph'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function usePromoteFact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, reason }: { code: string; reason: string }) =>
      api.facts.promote(code, reason),
    onSuccess: (_data, { code }) => {
      qc.invalidateQueries({ queryKey: ['facts'] });
      qc.invalidateQueries({ queryKey: ['fact', code] });
      qc.invalidateQueries({ queryKey: ['graph'] });
    },
  });
}

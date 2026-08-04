import axios from 'axios';

const gatewayBaseURL =
  (import.meta.env.VITE_HRIS_GATEWAY_API_BASE_URL as string) ||
  ((import.meta.env.VITE_HRIS_CORE_API_BASE_URL as string) || 'http://localhost:8000');

export const useGraphqlGateway = String(import.meta.env.VITE_USE_GRAPHQL_GATEWAY || 'false').toLowerCase() === 'true';

const gatewayHttpClient = axios.create({
  baseURL: gatewayBaseURL,
  timeout: 15000,
  withCredentials: true,
});

export async function gatewayRequest<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  const response = await gatewayHttpClient.post('/graphql', { query, variables });
  const payload = response.data as {
    data?: T;
    errors?: Array<{ message?: string }>;
  };
  if (payload?.errors?.length) {
    const first = payload.errors[0]?.message || 'Gateway GraphQL request failed';
    throw new Error(first);
  }
  if (!payload?.data) {
    throw new Error('Gateway returned empty GraphQL data.');
  }
  return payload.data;
}


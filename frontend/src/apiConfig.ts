import axios from 'axios';
import { supabase } from "./lib/supabase";

const Api = axios.create({
  baseURL: import.meta.env.VITE_BACKEND_URL + '/api/v1',
});


  Api.interceptors.request.use(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async (config: any) => {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session?.access_token) {
          throw new Error("No valid session. User must be logged in.");
        }
      const token = session.access_token;
      config.headers['Authorization'] = `Bearer ${token}`;
    } catch (error) {
      console.error('Error fetching auth session:', error);
      // Propagate the error so the request is rejected instead of being
      // sent unauthenticated. Sending requests without an Authorization
      // header could leak data via misconfigured RLS or fall back to
      // anonymous/service-role permissions.
      throw error;
    }
    return config;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (error: any) => {
    return Promise.reject(error);
  },
);

Api.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error)
);

export default Api;

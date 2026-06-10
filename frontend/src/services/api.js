// frontend/src/services/api.js

import axios from 'axios';

// Force BOTH real physical iOS and Android devices to target your laptop's Wi-Fi IP
const BASE_URL = 'http://192.168.31.114:8000/api/';

// 1. Create a global, reusable Axios client instance
const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// A local in-memory variable to cache our security token at runtime
let userToken = null;

/**
 * Sets or clears the active authorization token in memory for all future network outgoing packets.
 */
const setAuthToken = (token) => {
  userToken = token;
};

// 2. Attach a Request Interceptor
apiClient.interceptors.request.use(
  (config) => {
    if (userToken) {
      config.headers.Authorization = `Token ${userToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Explicit named exports so the bundler never gets confused with .default matching
export { apiClient, setAuthToken };

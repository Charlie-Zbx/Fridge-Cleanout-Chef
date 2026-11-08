import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:90000,fullyParallel:false,workers:1,use:{baseURL:process.env.KITCHEN_E2E_URL||'http://127.0.0.1:8000',headless:true,channel:'msedge',screenshot:'only-on-failure',serviceWorkers:'block'},reporter:'list'});

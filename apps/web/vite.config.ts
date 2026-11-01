import {defineConfig,loadEnv} from 'vite'; import vue from '@vitejs/plugin-vue';
export default defineConfig(({mode})=>{
 const env=loadEnv(mode,'.','VITE_');
 return {plugins:[vue()],server:{proxy:{'/api':env.VITE_API_PROXY_TARGET||'http://127.0.0.1:8001'}},build:{outDir:'dist'}}
});

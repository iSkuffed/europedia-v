import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { linkTip } from './lib/production';
import { initTooltips } from './lib/tooltip';

initTooltips(linkTip);
mount(App, {target: document.getElementById('app')!});

import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { linkTip } from './lib/production';
import { initTooltips } from './lib/tooltip';
import { cardTip } from './lib/cards';

initTooltips(el => cardTip(el) || linkTip(el));
mount(App, {target: document.getElementById('app')!});

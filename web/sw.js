'use strict';
// No fetch handler or offline cache: never retain dashboard sessions, files or secrets.
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('push',event=>{
 let value={};try{value=event.data?.json()||{};}catch{value={};}
 const title=typeof value.title==='string'?value.title.slice(0,80):'FreeQNAP health notification',body=typeof value.body==='string'?value.body.slice(0,240):'Open your trusted FreeQNAP dashboard to review local health.';
 event.waitUntil(self.registration.showNotification(title,{body,icon:'/icon-192.png',badge:'/icon-192.png',tag:'freeqnap-'+String(value.event_id||'health').slice(0,64),data:{path:'/#alerts'}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();const target=new URL('/#alerts',self.location.origin).href;
 event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients=>{for(const client of clients){if(new URL(client.url).origin===self.location.origin){await client.navigate(target);return client.focus();}}return self.clients.openWindow(target);}));
});

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={};vm.runInNewContext(fs.readFileSync('web/navigation.js','utf8'),context);
test('old bookmarks and nested settings resolve without losing their tools',()=>{for(const name of ['network','vpn','ddns','agents','backups']){assert.equal(context.workspaceRoute('#settings/'+name),name);assert.equal(context.workspaceRoute('#'+name),name);assert.equal(context.workspaceParent(name),'settings');}assert.equal(context.workspaceRoute('#storage/recovery'),'recovery');assert.equal(context.workspaceParent('recovery'),'storage');});
test('main menu contains collections while administrative sections are nested',()=>{const text=fs.readFileSync('web/index.html','utf8').split('<nav aria-label="NAS workspaces">')[1].split('</nav>')[0];for(const old of ['network','vpn','ddns','agents','backups','recovery'])assert.ok(!text.includes('href="#'+old+'"'));assert.ok(text.includes('href="#myradio"'));assert.ok(text.includes('Storage &amp; RAID'));});

test('photo sharing stays inside Photos and radio sharing stays inside My Radio',()=>{const html=fs.readFileSync('web/index.html','utf8');assert.ok(!html.includes('href="#shared"'));assert.ok(fs.readFileSync('web/photos.js','utf8').includes('#photos?view=shared'));assert.ok(fs.readFileSync('web/myradio.js','utf8').includes('#myradio?tab=shared'));});

test('offline account prompt is limited to initial console entry',()=>{assert.equal(fs.readFileSync('web/app.js','utf8').split('maybeOfflineAccountPrompt().catch').length-1,1);});

test('saved provider settings do not render credential inputs until explicit editing',()=>{const text=fs.readFileSync('web/accounts.js','utf8');assert.ok(text.includes("action('Edit provider connection…',()=>{const f="));assert.ok(text.includes("'data-lpignore':'true'"));});

test('identity reauthentication is separate from new family credentials',()=>{const text=fs.readFileSync('web/accounts.js','utf8');assert.ok(text.includes('function confirmIdentityAssignment('));assert.ok(text.includes("username.readOnly=true"));assert.ok(text.includes("not the new family member’s password"));});

test('family overview uses personal cards and administrator login uses server landing',()=>{const app=fs.readFileSync('web/app.js','utf8');assert.ok(app.includes('overview:familyMember()?personalOverview:overview'));assert.ok(app.includes('if(!familyMember())sectionVisual(w,page)'));assert.ok(app.includes("result.landing_page||'/#overview'"));const text=fs.readFileSync('web/accounts.js','utf8');assert.ok(text.includes('Administrators always land on Overview.'));assert.ok(text.includes('function landingPageForm('));});

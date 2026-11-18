from pathlib import Path
import subprocess,re
p=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub/openscrub_web.py')
s=p.read_text(); donor=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show','ac28a2a:openscrub_web.py'],cwd=p.parent,text=True)
s=re.sub(r'<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> ac28a2a \(Add local detection type and output review filters\)\n',lambda m:m[1],s,flags=re.S)
s=s.replace('const groups={},zones=[];TRKMEM={};ROWCARD={};','const groups=Object.create(null),zones=[];TRKMEM={};ROWCARD={};')
s=s.replace('({id:x.i,category,zone,representative:x,members:TRKMEM[x.i]||[x.i]})','({id:x.i,category,realCategory:x.category,zone,representative:x,members:zone?[x.i]:TRKMEM[x.i]})')
s=s.replace('sections.push({category,zone,cards,ids:cards.map(c=>c.id)});','sections.push({category,zone,index:sections.length,cards,ids:cards.map(c=>c.id)});')
s=s.replace('const grouped={},items=[];','const grouped=new Map(),items=[];').replace('if(key)(grouped[key]=grouped[key]||[]).push(x);','if(key){if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(x);}')
s=s.replace('of Object.entries(grouped))','of grouped)')
s=s.replace('REVIEW_META={sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};','REVIEW_META={jobId:id,viewGen:gen,sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};')
a=donor.index(' <div class="row reviewfilters">');b=donor.index(' <div id="beslot">',a)
s=s.replace(' <div id="beslot"></div><div class="row reviewranges">',donor[a:b]+' <div id="beslot"></div><div class="row reviewranges">')
s=s.replace('<details data-review-zones ','<details id="reviewZones" data-review-zones ')
s=s.replace('⚠ ${section.ids.length} detection(s)','⚠ <span id="reviewZoneCount">${section.ids.length} of ${section.ids.length}</span> detection(s)')
s=s.replace('onclick="setAllZd(false)">Keep all visible</button></div>`;','onclick="setAllZd(false)">Keep all visible</button></div>\n   <div class="detscope">These actions affect all outside-zone detections, including filtered-out detections.</div>`;')
s=s.replace('else html+=`<h3 style=', 'else html+=`<section id="reviewSection${section.index}"><h3 style=')
s=s.replace('<span class="badge">${section.ids.length}</span>','<span class="badge" id="reviewCount${section.index}">${section.ids.length}</span>')
s=s.replace('data-cat="${detLabel(cat)}">Keep all visible</button></h3>`;', 'data-cat="${detLabel(cat)}">Keep all visible</button></h3>\n   <div class="detscope">Category actions affect all ${detLabel(CATDN[cat]||cat)} groups, including filtered-out groups.</div>`;')
s=s.replace("if(section.zone)html+='</details>';", "html+=section.zone?'</details>':'</section>';")
s=s.replace('REVIEW_SCHED.start();initMarquee();saveStatus(EDITS,EDITS.status);','refreshReviewFilters();REVIEW_SCHED.start();initMarquee();saveStatus(EDITS,EDITS.status);')
# Preserve the strict captured-owner bridge. Omitted matching IDs schedule the current set.
s=s.replace('if(matchingCardIds)s.matching=', 'if(matchingCardIds!==undefined)s.matching=')
a=donor.index('function reviewMatches(');b=donor.index('\nfunction detLabel',a)
f=donor[a:b].replace('REVIEW_META.byId[i]','REVIEW_META?.byId.get(i)').replace('REVIEW_META.cards','[...REVIEW_META.byId.values()]')
f=f.replace('cancelReviewMarquee();clearSel();','REVIEW_SCHED?.selectionCleanup?.();clearSel();')
f=f.replace(' const active=document.activeElement,focusedCard=active?.closest?.(".det");',' const matching=[];\n const active=document.activeElement,focusedCard=active?.closest?.(".det");')
f=f.replace('if(match){count++;','if(match){matching.push(c.id);count++;')
f=f.replace('if(node){if(!match&&focusedCard===node)lostFocus=true;node.hidden=!match;}','if(node&&!match&&focusedCard===node)lostFocus=true;')
f=f.replace(' if(lostFocus)outputControl.focus();',' if(lostFocus)outputControl.focus();\n refreshReviewVisibleSet({jobId:REVIEW_META.jobId,viewGen:REVIEW_META.viewGen,matchingCardIds:matching});')
# Filters own view-local state only; complete metadata and lookup owners stay C01.
reset='''let REVIEW_FILTER={jobId:null,viewGen:0,type:null,output:"all"};
function resetReviewView(){
 REVIEW_SCHED?.selectionCleanup?.();clearSel();TRKMEM={};ROWCARD={};REVIEW_META=null;
 REVIEW_FILTER={jobId:CUR,viewGen:VIEW_GEN,type:null,output:"all"};
}
'''
s=s.replace('function reviewDescriptors(rows){',reset+'function reviewDescriptors(rows){')
s=s.replace('function detLabel(s){',f+'\nfunction detLabel(s){')
old="""   if(!zones.open){for(const section of this.meta.sections)if(section.zone)
    for(const id of section.ids)selSet.delete(id);
    if(menuEl){menuEl.remove();menuEl=null;}if(selSet.size)showSelMenu(12,12);
   }this.schedule();"""
s=s.replace(old,'   if(this.owns())reviewZoneToggle(zones);')
s=s.replace("function finishDetChoices(){\n DET_DIRTY", "function finishDetChoices(){\n if(!EDITS.busy)saveStatus(EDITS,'Unsaved edits — save to include them in the render.');\n DET_DIRTY")
s=s.replace(' refreshReviewVisibleSet({jobId:CUR,viewGen:VIEW_GEN});',' refreshReviewFilters();')
s=s.replace(" if(!EDITS.busy)saveStatus(EDITS,'Unsaved edits — save to include them in the render.');\n if(!DET_BATCH)", ' if(!DET_BATCH)')
s=s.replace('let selSet=new Set(),marqEl=null,menuEl=null,mStart=null,marqCancel=null;\nfunction cancelReviewMarquee(){if(marqCancel)marqCancel();}', 'let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;')
s=s.replace('  clearSel();owner.gesture=true;', '  owner.selectionCleanup?.();clearSel();owner.gesture=true;')
s=s.replace(".filter(b=>b.card.dataset.focusPin!=='1'&&", ".filter(b=>reviewSelectable(b.id)&&b.card.dataset.focusPin!=='1'&&")
s=s.replace('if(!owner.valid(b,false))continue;', 'if(!owner.valid(b,false)||!reviewSelectable(b.id))continue;')
s=s.replace('if(rect.left<r.right&&rect.right>r.left&&rect.top<r.bottom&&rect.bottom>r.top)', 'if(rect.width&&rect.height&&rect.left<r.right&&rect.right>r.left&&rect.top<r.bottom&&rect.bottom>r.top)')
s=s.replace('function bulkSet(blur){applyDetBatch([...selSet].filter(i=>REVIEW_META?.byId.has(i)),blur);clearSel();}', 'function bulkSet(blur){const ids=[...selSet].filter(reviewSelectable);clearSel();applyDetBatch(ids,blur);}')
p.write_text(s)

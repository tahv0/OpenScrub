"""Generation revalidation shares the review scheduler's binding and body owners."""
from test_thumbnail_scheduling import NETWORK, run


def test_obsolete_image_waits_for_its_body_and_revalidates_once():
    run(NETWORK + """
    const V='a'.repeat(32), NEXT='b'.repeat(32), THIRD='c'.repeat(32);
    const rows=[row(0,true,'face',-1,8,.9),row(1,true,'face',-1,8,.5),row(2),row(3),row(4),row(5)]
      .map(x=>({...x,thumbnail_row:String(x.i).repeat(64)}));
    const s=scheduler(),sections=reviewDescriptors(rows);
    s.meta.sections=sections;s.meta.byId=new Map(sections.flatMap(d=>d.cards.map(c=>[c.id,c])));
    s.meta.thumbnails={version:V,rows:new Map(rows.map(x=>[x.i,x.thumbnail_row])),
      attempted:false,incompatible:new Set()};
    for(const i of [0,2,3,4,5])bind(s,i);
    eligible(s,[0,2,3,4,5]);
    eq(tasks.length,4);if(tasks.some(t=>!t.url.includes('v='+V)))throw Error('request omitted generation');
    let errorBody;
    tasks[0].resolve({ok:false,status:409,json:()=>new Promise(resolve=>errorBody=resolve)});
    await tick();eq(THUMB_FLIGHTS.size,4);eq(tasks.length,4);
    errorBody({error:'thumbnail_obsolete',refresh:'detections'});await tick();
    const meta=tasks.find(t=>t.url.endsWith('/detections'));
    if(!meta)throw Error('obsolete image did not request metadata');
    eq(meta.options.cache,'no-store');
    tasks[1].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    eq(tasks.filter(t=>t.url.endsWith('/detections')).length,1);
    meta.resolve({ok:true,json:async()=>({duration:20,thumbnail_version:NEXT,
      detections:rows.map(x=>x.i===1?{...x,thumbnail_row:'f'.repeat(64)}:x)})});
    await tick();
    if(tasks.some(t=>t.url.includes('/thumb/0')&&t.url.includes('v='+NEXT)))throw Error('changed group was rebound');
    if(!tasks.some(t=>t.url.includes('/thumb/2')&&t.url.includes('v='+NEXT)))throw Error('unchanged row did not advance');
    if(!tasks[2].options.signal.aborted||!tasks[3].options.signal.aborted)throw Error('old fetches still own bindings');
    await headers(tasks[2]);await body(tasks[2]);await headers(tasks[3]);await body(tasks[3]);
    eq(created,[]);eq(THUMB_FLIGHTS.size,4);
    const newTask=tasks.find(t=>t.url.includes('/thumb/2')&&t.url.includes('v='+NEXT));
    newTask.resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete',version:THIRD})});await tick();
    eq(tasks.filter(t=>t.url.endsWith('/detections')).length,1);
    """)


def test_generation_owner_fences_review_replacement():
    run(NETWORK + """
    function owned(){
      const s=scheduler(),rows=[{...row(2),thumbnail_row:'2'.repeat(64)}],sections=reviewDescriptors(rows);
      s.meta.sections=sections;s.meta.byId=new Map(sections.flatMap(d=>d.cards.map(c=>[c.id,c])));
      s.meta.thumbnails={version:'a'.repeat(32),rows:new Map([[2,'2'.repeat(64)]]),
        attempted:false,incompatible:new Set()};
      bind(s,2);eligible(s,[2]);return {s,rows};
    }
    const {s,rows}=owned();
    tasks[0].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    const obsolete=tasks[1];
    if(!obsolete?.url.endsWith('/detections'))throw Error('obsolete image did not request metadata');
    openJob('B');openJob('A');const {s:current}=owned();
    eq(obsolete.options.signal.aborted,true);
    obsolete.resolve({ok:true,json:async()=>({duration:20,detections:rows,thumbnail_version:'b'.repeat(32)})});await tick();
    eq(current.meta.thumbnails.version,'a'.repeat(32));eq(created,[]);eq(tasks.length,3);
    await headers(tasks[2]);await body(tasks[2]);eq(created.length,1);
    """)


def test_failed_recovery_spends_mount_budget_and_preserves_drafts():
    run(NETWORK + """
    const s=scheduler(), rows=[{...row(0),thumbnail_row:'0'.repeat(64)}],sections=reviewDescriptors(rows);
    s.meta.sections=sections;s.meta.byId=new Map(sections.flatMap(d=>d.cards.map(c=>[c.id,c])));
    s.meta.thumbnails={version:'a'.repeat(32),rows:new Map([[0,rows[0].thumbnail_row]]),attempted:false,incompatible:new Set()};
    const draft=EDITS,editor=BE,manual=MAN;MAN.push({manual_id:'held'});
    bind(s,0);eligible(s,[0]);
    tasks[0].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    const recovery=tasks[1];recovery.reject(Error('offline'));await tick();
    eq(s.meta.thumbnails.attempted,true);eq(s.meta.thumbnails.version,'a'.repeat(32));
    s.recoverThumbnails();await tick();eq(tasks.length,2);
    if(EDITS!==draft||BE!==editor||MAN!==manual||MAN[0].manual_id!=='held')throw Error('draft ownership changed');
    """)


def test_group_membership_changes_prevent_rebinding_while_unchanged_rows_advance():
    run(NETWORK + """
    const rows=[row(0,true,'face',-1,8,.9),row(1,true,'face',-1,8,.5),row(2)]
      .map(x=>({...x,thumbnail_row:String(x.i).repeat(64)}));
    const s=scheduler(),sections=reviewDescriptors(rows);
    s.meta.sections=sections;s.meta.byId=new Map(sections.flatMap(d=>d.cards.map(c=>[c.id,c])));
    s.meta.thumbnails={version:'a'.repeat(32),rows:new Map(rows.map(x=>[x.i,x.thumbnail_row])),attempted:false,incompatible:new Set()};
    bind(s,0);bind(s,2);eligible(s,[0,2]);
    tasks[0].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    tasks[2].resolve({ok:true,json:async()=>({duration:20,thumbnail_version:'b'.repeat(32),detections:[...rows,{...row(3,true,'face',-1,8),thumbnail_row:'3'.repeat(64)}]})});await tick();
    eq(s.meta.thumbnails.incompatible.has(0),true);eq(s.meta.thumbnails.incompatible.has(2),false);
    tasks[1].reject(Error('aborted'));await tick();
    if(tasks.some(t=>t.url.includes('/thumb/0')&&t.url.includes('v='+('b'.repeat(32)))))throw Error('changed group rebound');
    if(!tasks.some(t=>t.url.includes('/thumb/2')&&t.url.includes('v='+('b'.repeat(32)))))throw Error('unchanged row did not advance');
    """)

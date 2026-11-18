"""View filters evaluate the shipped JavaScript, not a second predicate model."""
from test_review_choices import DOM, run as run_choices

FILTER_DOM = r"""
const oldCreate=document.createElement;
document.createElement=(tag)=>{const e=oldCreate(tag);e.isConnected=true;e.focus=()=>document.activeElement=e;
 e.closest=()=>null;e.contains=x=>x===e;return e;};
const fixture=[row(0,true,'face',0,-1,.9),row(1,false,'face',0),row(2,true,'face',0),
 row(3,true,'face'),row(4,false,'plate',-1,4,.9),row(5,false,'plate',-1,4),
 row(6,true,'plate'),row(7,false,'email'),row(8,false,'face',0,-1,.95,true),
 row(9,true,'plate',-1,4,.95,true)];
const ids=()=>[...REVIEW_META.byId.values()].filter(c=>reviewMatches(c,REVIEW_FILTER.type,REVIEW_FILTER.output)).map(c=>c.id).sort((a,b)=>a-b);
const status=()=>elements.get('reviewFilterStatus').textContent;
"""


def run(scenario):
    run_choices(FILTER_DOM + scenario)


def test_native_filters_and_exact_mixed_card_oracle():
    run("""await review(fixture);
    if(!mounted.includes('id="reviewType"')||!mounted.includes('id="reviewOutput"'))throw Error('missing native review selectors');
    eq(ids(),[0,3,4,6,7,8,9]);eq(status(),'7 of 7 cards match');
    setReviewFilter(null,'blur');eq(ids(),[0,3,6,9]);eq(status(),'4 of 7 cards match');
    setReviewFilter(null,'visible');eq(ids(),[0,4,7,8]);
    setReviewFilter('face','all');eq(ids(),[0,3,8]);
    setReviewFilter('face','blur');eq(ids(),[0,3]);
    setReviewFilter('face','visible');eq(ids(),[0,8]);
    setReviewFilter('plate','all');eq(ids(),[4,6,9]);
    setReviewFilter('plate','blur');eq(ids(),[6,9]);
    setReviewFilter('plate','visible');eq(ids(),[4]);
    setReviewFilter('email','blur');eq(ids(),[]);eq(elements.get('reviewFilterEmpty').hidden,false);
    eq(TRKMEM[0],[0,1,2]);eq(ROWCARD[8],8);eq(REVIEW_META.byId.get(8).members,[8]);
    """)


def test_conditional_counts_pending_overlay_false_representative_and_unknown_categories():
    run("""const altered=fixture.map(x=>({...x}));altered[0].enabled=false;
    openJob('A');EDITS.enabled[0]=true;EDITS.enabled[1]=false;
    const pending=loadReview();await reply({duration:5,detections:altered});await pending;
    setReviewFilter('face','visible');
    const types=elements.get('reviewType').innerHTML,outputs=elements.get('reviewOutput').innerHTML;
    if(!types.includes('face (2)')||!types.includes('plate (1)')||!outputs.includes('All outputs (3)')||!outputs.includes('Includes blurred appearances (2)'))throw Error('wrong conditional option counts');
    applyDet(0,false);eq(ids(),[0,8]);setReviewFilter('face','blur');eq(ids(),[3]);
    const extra=row(10,true,`custom \"<&'`,0,-1,.5,true);await review([...fixture,extra]);
    setReviewFilter(extra.category,'all');eq(ids(),[10]);
    if(!elements.get('reviewType').innerHTML.includes('&lt;&amp;'))throw Error('category name not escaped');
    """)


def test_hidden_bulk_scopes_and_single_transaction_refresh():
    run("""await review(fixture);setReviewFilter('face','visible');
    let refreshes=0;const original=refreshReviewFilters;refreshReviewFilters=(...args)=>{refreshes++;return original(...args)};
    setAll('face',false);eq([0,1,2,3].map(i=>EN[i]),[false,false,false,false]);eq(EN[8],false);eq(EN[9],true);eq(refreshes,1);
    setAllZd(false);eq(EN[9],false);eq(EN[6],true);eq(refreshes,2);
    setReviewFilter('face','all');selSet.add(0);selSet.add(3);bulkSet(true);eq([0,1,2,3].map(i=>EN[i]),[true,true,true,true]);eq([...selSet],[]);
    """)


def test_filtering_is_local_retains_editor_and_resets_each_new_job():
    run("""await review(fixture);BE.ov[1]=[1,2,3,4];BE.times[1]=[0,1];BE.adds.push({box:[1,2,3,4]});
    BE.drag={i:1};BE.audio=[{t0:0,t1:1,mode:'mute'}];BE.sel=1;MAN.push({draft:true});
    const before=JSON.stringify({EN,EDITS,BE,MAN}),editor=BE,node=elements.get('beslot'),requests=calls.length;
    selSet.add(0);setReviewFilter('email','blur');eq([...selSet],[]);setReviewFilter(null,'all');
    eq(calls.length,requests);eq(JSON.stringify({EN,EDITS,BE,MAN}),before);eq(BE===editor,true);eq(elements.get('beslot')===node,true);
    setReviewFilter('plate','visible');openJob('B');eq([REVIEW_FILTER.type,REVIEW_FILTER.output],[null,'all']);openJob('A');eq([REVIEW_FILTER.type,REVIEW_FILTER.output],[null,'all']);
    """)


def test_selection_prunes_on_live_output_and_zone_close_without_resurrection():
    run("""await review(fixture);setReviewFilter(null,'blur');selSet.add(0);selSet.add(3);
    applyDet(0,false);eq([...selSet],[3]);
    setReviewFilter(null,'all');elements.get('reviewZones').open=true;selSet.add(8);selSet.add(3);
    elements.get('reviewZones').open=false;reviewZoneToggle();eq([...selSet],[3]);
    elements.get('reviewZones').open=true;reviewZoneToggle();eq([...selSet],[3]);
    """)


def test_no_detections_and_collapsed_zone_only_are_distinct():
    run("""await review([]);eq(status(),'0 of 0 cards match');eq(elements.get('reviewFilterEmpty').textContent,'No detections in this job.');
    await review([row(8,false,'face',0,-1,.5,true)]);eq(status(),'1 of 1 cards match');
    if(!elements.get('reviewFilterHint').textContent.includes('outside your zones'))throw Error('collapsed matches unexplained');
    """)


def test_many_group_counts_scan_once_per_bulk_transaction():
    run("""await review(Array.from({length:600},(_,i)=>row(i,true,'face',Math.floor(i/3))));
    let reads=0;const live=EN;EN=new Proxy(live,{get(o,k){reads++;return o[k]}});
    let scans=0;const old=refreshReviewFilters;refreshReviewFilters=(...a)=>{scans++;return old(...a)};
    setAll('face',false);eq(scans,1);if(reads>2400)throw Error('per-member full-list filter scan: '+reads);
    eq(status(),'200 of 200 cards match');
    """)


def test_false_mixed_representative_and_stale_zone_callback():
    run("""const r=fixture.map(x=>({...x}));r[1].confidence=.99;await review(r);
    eq(TRKMEM[1],[0,1,2]);setReviewFilter(null,'blur');eq(ids(),[1,3,6,9]);
    setReviewFilter(null,'visible');eq(ids(),[1,4,7,8]);
    let scans=0;const old=refreshReviewFilters;refreshReviewFilters=()=>{scans++;old()};
    reviewZoneToggle(document.createElement('details'));eq(scans,0);
    """)


def test_scheduler_matching_bridge_keeps_empty_and_rejects_stale_owner():
    run("""await review(fixture);const owner=REVIEW_SCHED;
    setReviewFilter('email','blur');eq([...owner.matching],[]);
    refreshReviewVisibleSet({jobId:owner.jobId,viewGen:owner.viewGen});
    refreshReviewVisibleSet();eq([...owner.matching],[]);
    setReviewFilter('face','visible');eq([...owner.matching],[8,0]);
    refreshReviewVisibleSet({jobId:'old',viewGen:owner.viewGen,matchingCardIds:[3]});
    eq([...owner.matching],[8,0]);
    let cancelled=0;owner.selectionCleanup=()=>{cancelled++;owner.selectionCleanup=null};
    selSet.add(0);setReviewFilter(null,'all');eq(cancelled,1);eq([...selSet],[]);
    eq(owner.meta.byId,REVIEW_META.byId);eq(owner.meta.byId.get(0).members,[0,1,2]);
    """)


def test_selected_action_retains_explicit_matching_ids_across_virtual_unmount():
    run("""await review(fixture);setReviewFilter('face','all');
    selSet.add(0);selSet.add(3);elements.delete('det3');
    bulkSet(false);eq([EN[0],EN[1],EN[2]],[false,false,false]);
    eq(EN[3],false);eq([...selSet],[]);
    """)

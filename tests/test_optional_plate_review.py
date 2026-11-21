"""Review must distinguish policy output from a human Keep or Blur."""
import json

from test_exact_samples import exact
from test_job_lifecycle import request, store
from test_review_choices import run
from test_report_transactions import tracker, track, join


def optional_report(exact):
    doc = json.loads(exact.path.read_text())
    doc['plate_policy_evidence_version'] = 1
    doc['provenance']['settings'].update(uncertain_policy='manual_review',
                                          plate_threshold=.1, plate_auto_cutoff=.8)
    base = dict(doc['detections'][0], category='plate', text='plate',
                cbox=[1,2,8,9], confidence=.9, dense=True, track=3)
    doc['detections'] = [
        dict(base, t_start=.2, t_end=.25, enabled=False,
             policy_evidence={'origin':'detection','frame':1,'geometry_valid':True}),
        dict(base, t_start=.4, t_end=.45, enabled=True,
             policy_evidence={'origin':'detection','frame':2,'geometry_valid':True}),
        dict(base, t_start=.25, t_end=.4, enabled=False,
             policy_evidence={'origin':'interpolation','frame':None,'geometry_valid':False}),
        dict(base, t_start=.6, t_end=.65, enabled=False, output_choice='keep',
             policy_evidence={'origin':'detection','frame':3,'geometry_valid':True}),
    ]
    exact.path.write_text(json.dumps(doc))


def test_optional_review_metadata_reports_unhandled_observations_and_gaps(exact):
    optional_report(exact)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    value = response.json
    assert value['plate_policy'] == {'uncertain_policy':'manual_review',
                                     'plate_threshold':.1, 'plate_auto_cutoff':.8}
    rows = value['detections']
    assert [row['policy_status'] for row in rows] == ['suggestion','automatic','gap','keep']
    assert [row['policy_geometry_supported'] for row in rows] == [True,True,False,True]
    assert all('output_choice' not in row for row in rows[:3])
    assert rows[3]['output_choice'] == 'keep'


def test_ordinary_review_metadata_does_not_acquire_optional_fields(exact):
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    assert 'plate_policy' not in response.json
    assert all('policy_status' not in row and 'output_choice' not in row
               for row in response.json['detections'])


def test_review_card_keeps_automatic_suggestions_distinct_from_explicit_choices():
    run("""const optional=[
      {...row(0,false,'plate',-1,7,.4),policy_status:'suggestion',policy_geometry_supported:true},
      {...row(1,true,'plate',-1,7,.9),policy_status:'automatic',policy_geometry_supported:true},
      {...row(2,false,'plate',-1,7,.1),policy_status:'gap',policy_geometry_supported:false}];
    await review(optional);
    const text=()=>elements.get('ds1').textContent;
    if(!text().includes('1 uncertain observation remains unmasked'))throw Error('unhandled suggestion not labeled: '+text());
    if(!text().includes('1 unsupported sample'))throw Error('unsupported sample not labeled: '+text());
    if(!text().includes('1 automatic mask'))throw Error('automatic output not labeled: '+text());
    eq(elements.get('bb1').getAttribute('aria-pressed'),'false');
    eq(elements.get('kb1').getAttribute('aria-pressed'),'false');
    if(!mounted.includes('3 samples'))throw Error('synthetic rows mislabeled as frames');
    click('kb1');eq(EDITS.enabled,{0:false,1:false,2:false});
    eq(elements.get('kb1').getAttribute('aria-pressed'),'true');
    if(text().includes('uncertain observation'))throw Error('explicit Keep still called unhandled');
    click('bb1');eq(EDITS.enabled,{0:true,1:true,2:true});
    eq(elements.get('bb1').getAttribute('aria-pressed'),'true');
    if(!text().includes('unsupported sample cannot be blurred without mask geometry'))throw Error('missing honest gap warning: '+text());
    if(!text().includes('2 of 3 samples will be blurred'))throw Error('unsupported position counted as output: '+text());
    """)


def test_blur_choice_is_visible_on_later_mixed_plate_cards_without_overstating_coverage():
    run("""const mixed=Array.from({length:8},(_,i)=>{
      const valid=i%2===0;
      return {...row(i,valid,'plate',-1,40+Math.floor(i/2),valid?.9:.1),
        policy_status:valid?'automatic':'gap',policy_geometry_supported:valid};
    });
    await review(mixed);setReviewFilter(null,'blur');
    eq([...REVIEW_SCHED.matching].sort((a,b)=>a-b),[0,2,4,6]);
    for(const i of [0,2,4,6]){
      click('bb'+i);
      eq(elements.get('bb'+i).getAttribute('aria-pressed'),'true');
      eq(REVIEW_META.byId.get(i).members,[i,i+1]);
      const c=REVIEW_META.byId.get(i);
      eq(reviewOn(c,i),true);eq(reviewOn(c,i+1),false);
      if(!elements.get('ds'+i).textContent.includes('1 of 2 samples will be blurred'))throw Error('unsupported sample hidden');
      if(!elements.get('ds'+i).textContent.includes('cannot be blurred without mask geometry'))throw Error('gap warning hidden');
    }
    // A just-decided card stays in place until the filter changes, so the
    // grid never re-flows under the pointer; a filter change then drops it.
    click('kb4');eq(REVIEW_SCHED.matching.has(4),true);
    eq([EN[4],EN[5]],[false,false]);
    setReviewFilter(null,'blur');eq(REVIEW_SCHED.matching.has(4),false);
    """)


def test_exact_editor_does_not_present_unsupported_or_other_frame_positions(exact):
    optional_report(exact)
    at_first = request('get', exact.url + '/edit_sample?t=0.2')
    assert at_first.status_code == 200
    assert [(row['i'], row['enabled']) for row in at_first.json['boxes']] == [(0, False)]
    at_second = request('get', exact.url + '/edit_sample?t=0.4')
    assert at_second.status_code == 200
    assert [(row['i'], row['enabled']) for row in at_second.json['boxes']] == [(1, True)]


def test_same_value_keep_acknowledgement_stays_explicit_when_card_refreshes():
    run("""const optional=[{...row(0,false,'plate',-1,-1,.4),
      policy_status:'suggestion',policy_geometry_supported:true}];
    await review(optional);click('kb0');const save=saveAndRender();
    await reply();refreshDet(0);
    eq(elements.get('kb0').getAttribute('aria-pressed'),'true');
    if(elements.get('ds0').textContent.includes('uncertain observation'))throw Error('acknowledged Keep reverted to suggestion');
    await reply();await save;
    """)


def test_newer_keep_survives_older_blur_ack_for_optional_candidate():
    run("""const optional=[{...row(0,false,'plate',-1,-1,.4),
      policy_status:'suggestion',policy_geometry_supported:true}];
    await review(optional);click('bb0');const first=saveAndRender();
    click('kb0');await reply();await first;
    eq(EDITS.enabled,{0:false});refreshDet(0);
    eq(elements.get('kb0').getAttribute('aria-pressed'),'true');
    const retry=saveAndRender();await reply();refreshDet(0);
    eq(elements.get('kb0').getAttribute('aria-pressed'),'true');
    if(elements.get('ds0').textContent.includes('uncertain observation'))throw Error('saved Keep became unhandled');
    await reply();await retry;
    """)


def test_unsupported_blur_intent_never_counts_as_rendered_output():
    run("""const optional=[{...row(0,false,'plate',-1,-1,.4),
      policy_status:'gap',policy_geometry_supported:false}];
    await review(optional);click('bb0');
    eq(elements.get('bb0').getAttribute('aria-pressed'),'true');
    const card=REVIEW_META.byId.get(0);
    eq(reviewMatches(card,null,'blur'),false);
    eq(reviewMatches(card,null,'visible'),true);
    if(!elements.get('ds0').textContent.includes('0 of 1 samples will be blurred'))throw Error('gap counted as output');
    if(!elements.get('ds0').textContent.includes('cannot be blurred without mask geometry'))throw Error('missing unsupported geometry notice');
    """)


def test_malformed_optional_settings_leave_review_available_with_unknown_policy(exact):
    optional_report(exact)
    for settings in (None, [], {}, {'uncertain_policy':'unknown'},
                     {'uncertain_policy':'manual_review','plate_threshold':.9,'plate_auto_cutoff':.8}):
        doc=json.loads(exact.path.read_text())
        doc['provenance']['settings']=settings
        exact.path.write_text(json.dumps(doc))
        response=request('get', exact.url+'/detections')
        assert response.status_code==200
        assert response.json['plate_policy']['uncertain_policy']=='unavailable'
        assert all(row['policy_status']=='unknown' for row in response.json['detections'])


def test_missing_optional_provenance_leaves_review_available(exact):
    optional_report(exact)
    doc=json.loads(exact.path.read_text())
    doc.pop('provenance')
    exact.path.write_text(json.dumps(doc))
    response=request('get', exact.url+'/detections')
    assert response.status_code==200
    assert response.json['plate_policy']['uncertain_policy']=='unavailable'


def test_ordinary_manual_addition_remains_available_with_old_settings(exact):
    doc=json.loads(exact.path.read_text());doc['provenance']['settings']='old'
    exact.path.write_text(json.dumps(doc))
    response=request('post', exact.url+'/detections', json={
        'manual':[{'t_start':0,'t_end':1,'screen_box':[2,3,9,10]}]})
    assert response.status_code==200
    row=json.loads(exact.path.read_text())['detections'][-1]
    assert row['category']=='manual' and row['enabled'] is True
    assert 'output_choice' not in row


def test_unknown_policy_status_never_claims_a_saved_mask_is_automatic():
    run("""const optional=[{...row(0,true,'plate',-1,-1,.9),
      policy_status:'unknown',policy_geometry_supported:true}];
    await review(optional);
    const text=elements.get('ds0').textContent;
    if(!text.includes('policy unavailable'))throw Error('unknown policy was not disclosed: '+text);
    if(text.includes('will be blurred')||text.includes('automatic mask'))throw Error('unknown policy guessed output: '+text);
    const card=REVIEW_META.byId.get(0);
    eq(reviewMatches(card,null,'all'),true);
    eq(reviewMatches(card,null,'blur'),false);eq(reviewMatches(card,null,'visible'),false);
    eq(elements.get('bb0').getAttribute('aria-pressed'),'false');
    eq(elements.get('kb0').getAttribute('aria-pressed'),'false');
    """)


def test_ordinary_track_remains_available_with_old_settings(store, tracker):
    doc=json.loads(store.path.read_text());doc['provenance']['settings']='old'
    store.path.write_text(json.dumps(doc))
    entered, release, threads, _ = tracker
    assert track(store).status_code == 200
    assert entered.wait(5)
    release.set()
    join(threads[0])
    row=json.loads(store.path.read_text())['detections'][-1]
    assert row['category']=='manual' and row['enabled'] is True
    assert 'output_choice' not in row


def test_invalid_source_provenance_keeps_existing_thumbnail_refusal(exact):
    doc=json.loads(exact.path.read_text())
    doc['provenance']=None
    exact.path.write_text(json.dumps(doc))
    ordinary=request('get', exact.url+'/detections')
    doc['plate_policy_evidence_version']=1
    exact.path.write_text(json.dumps(doc))
    optional=request('get', exact.url+'/detections')
    assert ordinary.status_code==optional.status_code==500
    assert ordinary.json==optional.json
    assert ordinary.json['error']=='thumbnail_invalid_report'


def test_ordinary_review_does_not_filter_rows_or_card_members_for_policy():
    run("""openJob('A');
    const input=Array.from({length:3000},(_,i)=>row(i,true,'face',-1,i,.8));
    const original=Array.prototype.filter;let rowPasses=0,memberPasses=0;
    Array.prototype.filter=function(...args){
      if(this===input)rowPasses++;
      if(this.length&&this.every(x=>Number.isInteger(x)))memberPasses++;
      return original.apply(this,args);
    };
    let sections;try{sections=reviewDescriptors(input);}finally{Array.prototype.filter=original;}
    eq(sections[0].cards.length,3000);
    if(rowPasses||memberPasses)throw Error(`ordinary policy passes: ${rowPasses} rows, ${memberPasses} cards`);
    """)


def test_mixed_review_keeps_policy_metadata_on_its_own_card():
    run("""openJob('A');
    const policy={...row(0,false,'plate',-1,7,.4),policy_status:'suggestion',policy_geometry_supported:true};
    const ordinary=row(1,true,'face',-1,8,.8);
    const sections=reviewDescriptors([policy,ordinary]);
    const cards=sections.flatMap(s=>s.cards);
    eq(cards.find(c=>c.realCategory==='plate').policyRows.get(0),policy);
    eq(cards.find(c=>c.realCategory==='face').policyRows,undefined);
    """)

"""Review cards say at a glance whether they still need a human decision."""
from test_review_choices import run


def test_policy_cards_label_review_need_and_explicit_choices():
    run("""const plate=(i,status,supported=true,track=7)=>({...row(i,status==='automatic','plate',-1,track,.5),
      policy_status:status,policy_geometry_supported:supported});
    await review([plate(0,'suggestion'),plate(1,'automatic'),plate(2,'gap',false),
                  plate(3,'automatic',true,8),plate(4,'automatic',true,8)]);
    const label=i=>[elements.get('dl'+i).textContent,elements.get('dl'+i).dataset.state,
                    elements.get('det'+i).dataset.state,elements.get('dl'+i).hidden];
    // card 0 = rows 0-2 (track 7), card 3 = rows 3-4 (track 8)
    eq(label(0),['Needs review','review','review',false]);     // an uncertain suggestion is undecided
    eq(label(3),['Blurred automatically','blur','blur',false]);
    click('kb0');eq(label(0),['Kept visible','keep','keep',false]);
    click('bb0');eq(label(0),['Blurred — has gaps','review','review',false]);
    if(!elements.get('ds0').textContent.includes('cannot be blurred without mask geometry'))
      throw Error('detail line lost the gap warning');
    click('bb3');eq(label(3),['Blurred','blur','blur',false]);
    """)


def test_unknown_policy_always_needs_review():
    run("""await review([{...row(0,true,'plate',-1,7),policy_status:'unknown',policy_geometry_supported:true}]);
    eq(elements.get('dl0').textContent,'Needs review');
    click('bb0');eq(elements.get('dl0').textContent,'Needs review');
    """)


def test_ordinary_cards_keep_their_text_and_color_the_card():
    run("""await review([row(0,true,'face'),row(1,false,'face')]);
    eq(elements.get('dl0').hidden===false,false);  // never revealed for ordinary cards
    eq(elements.get('ds0').textContent,'Will be blurred');eq(elements.get('det0').dataset.state,'blur');
    click('kb0');eq(elements.get('ds0').textContent,'Will stay visible');eq(elements.get('det0').dataset.state,'keep');
    """)


def test_decided_card_stays_until_the_filter_changes():
    run("""await review([row(0,true,'face'),row(1,true,'face'),row(2,true,'face')]);
    setReviewFilter(null,'blur');eq([...REVIEW_SCHED.matching].sort(),[0,1,2]);
    click('kb1');eq([...REVIEW_SCHED.matching].sort(),[0,1,2]);
    eq(REVIEW_FILTER.held.has(1),true);
    setReviewFilter(null,'blur');eq([...REVIEW_SCHED.matching].sort(),[0,2]);
    eq(REVIEW_FILTER.held.size,0);
    """)


def test_bulk_actions_still_refilter():
    run("""await review([row(0,true,'face'),row(1,true,'face'),row(2,true,'email')]);
    setReviewFilter(null,'blur');
    setAll('face',false);eq([...REVIEW_SCHED.matching].sort(),[2]);
    eq(REVIEW_FILTER.held.size,0);
    click('bb2');click('kb2');eq([...REVIEW_SCHED.matching].sort(),[2]);  // a single click still holds
    """)

"""Full-module behavioral controls for the disposable Task114 experiment."""
import hashlib, importlib.util, os, pathlib, sys
import pytest
from rapidfuzz import fuzz

PATH=pathlib.Path(os.environ['TASK114_MODULE']).resolve()
assert hashlib.sha256(PATH.read_bytes()).hexdigest()==os.environ['TASK114_MODULE_SHA']
spec=importlib.util.spec_from_file_location('task114_active',PATH)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
assert pathlib.Path(m.__file__).resolve()==PATH

def record(t,end,box,cat='email',text='abcdefghij',conf=.99,off=(0.,0.),last=0.,dense=False,track=-1,person=-1,poly=()):
    return {'t_start':t,'t_end':end,'cbox':box,'category':cat,'text':text,
            'confidence':conf,'aoff':off,'last_seen':last,'dense':dense,
            'track':track,'person':person,'poly':poly}
def det(t,box=(0,0,10,10),**kw):return m.Detection(**record(t,t,box,**kw))
def check(out, objects, expected, inputs, input_expected):
    assert len(out)==len(objects)
    assert all(a is b for a,b in zip(out,objects))
    assert [vars(d) for d in out]==expected
    assert [vars(d) for d in inputs]==input_expected

def test_newest_birth_wins_despite_older_recent_update():
    a=det(0);b=det(1,(30,0,40,10));c=det(2);d=det(3,(15,0,25,10))
    inputs=[a,b,c,d];out=m.merge_detections(inputs,10,fuzz=fuzz)
    ra=record(0,12,(0,0,10,10),last=2);rb=record(1,13,(15,0,40,10),last=3)
    check(out,[a,b],[ra,rb],inputs,[ra,rb,record(2,12,(0,0,10,10),last=2),record(3,13,(15,0,25,10),last=3)])

def test_ordered_fallthrough_retains_callback_arguments():
    a=det(0);b=det(1,(30,0,40,10));c=det(2);d=det(10,(15,0,25,10));calls=[]
    def verify(obj,start,end):calls.append((obj,start,end));return obj is a
    inputs=[a,b,c,d];out=m.merge_detections(inputs,.5,bridge_gap=2,fuzz=fuzz,gap_check=verify)
    assert len(calls)==2 and calls[0][0] is b and calls[1][0] is a
    assert [c[1:] for c in calls]==[(1,10),(2,10)]
    ra=record(0,10.5,(0,0,25,10),last=10);rb=record(1,1.5,(30,0,40,10),last=1)
    check(out,[a,b],[ra,rb],inputs,[ra,rb,record(2,2.5,(0,0,10,10),last=2),record(10,10.5,(15,0,25,10),last=10)])

@pytest.mark.parametrize('boxes,union',[
    ([(0,0,10,10),(20,0,30,10),(40,0,50,10)],(0,0,50,10)),
    ([(40,0,50,10),(20,0,30,10),(0,0,10,10)],(0,0,50,10)),
    ([(-50,-10,-40,0),(-30,-10,-20,0),(-10,-10,0,0)],(-50,-10,0,0))])
def test_union_growth_and_negative_coordinates(boxes,union):
    inputs=[det(t,b) for t,b in zip((0,.1,.2),boxes)]
    out=m.merge_detections(inputs,.8,fuzz=fuzz)
    ra=record(0,1.,union,last=.2)
    check(out,[inputs[0]],[ra],inputs,[ra,record(.1,.9,boxes[1],last=.1),record(.2,1.,boxes[2],last=.2)])

@pytest.mark.parametrize('x,merge',[(22,True),(22.00001,False),(-22,True),(-22.00001,False)])
def test_inclusive_twelve_pixel_slack(x,merge):
    a=det(0);b=det(.1,(x,0,x+10,10));inputs=[a,b]
    out=m.merge_detections(inputs,1,fuzz=fuzz)
    rb=record(.1,1.1,(x,0,x+10,10),last=.1)
    ra=record(0,1.1 if merge else 1,(min(0,x),0,max(10,x+10),10) if merge else (0,0,10,10),last=.1 if merge else 0)
    check(out,[a] if merge else [a,b],[ra] if merge else [ra,rb],inputs,[ra,rb])

def test_equal_times_unordered_input_and_equal_distinct_objects_keep_stable_identity():
    a=det(0);b=det(0);later=det(2,(100,0,110,10));inputs=[later,b,a]
    out=m.merge_detections(inputs,.8,fuzz=fuzz)
    rb=record(0,.8,(0,0,10,10));rl=record(2,2.8,(100,0,110,10),last=2)
    check(out,[b,later],[rb,rl],inputs,[rl,rb,rb])

@pytest.mark.parametrize('left,right,ff,merge',[
    ('abcdefghij','abcdefgXYZ',fuzz,True),
    ('abcdefghij','abcdefWXYZ',fuzz,False),
    ('abcdefghij','prefixabcdefghijsuffix',fuzz,True),
    ('abcdefghijklmnopqrst','ZZZZZZZZZZZZZZZabcdeXghijXlmnoXqrstZZZZZZZZZZZZZZZ',fuzz,True),
    ('abcdefghijklmnopqrst','ZZZZZZZZZZZZZZZabcdeXghijXlmnoXXrstZZZZZZZZZZZZZZZ',fuzz,False),
    ('','unrelated',fuzz,True),('unrelated','',fuzz,True),
    ('abcdefghij','unrelated',None,True)])
def test_original_fuzzy_ratio_partial_and_bypasses(left,right,ff,merge):
    a=det(0,text=left);b=det(.1,text=right);inputs=[a,b]
    out=m.merge_detections(inputs,1,fuzz=ff)
    ra=record(0,1.1 if merge else 1,(0,0,10,10),text=left,last=.1 if merge else 0)
    rb=record(.1,1.1,(0,0,10,10),text=right,last=.1)
    check(out,[a] if merge else [a,b],[ra] if merge else [ra,rb],inputs,[ra,rb])

@pytest.mark.parametrize('gap,bridge,callback_result,merge,calls_n',[
    (.8,0,False,True,0),(.80001,0,False,False,1),
    (4,4,False,True,0),(4.00001,4,False,False,1),
    (100,4,True,True,1),(100,4,False,False,1)])
def test_hold_bridge_and_unlimited_visual_gap_contract(gap,bridge,callback_result,merge,calls_n):
    a=det(0);b=det(gap);calls=[]
    def visual(obj,start,end):calls.append((obj,start,end));return callback_result
    inputs=[a,b];out=m.merge_detections(inputs,.8,bridge_gap=bridge,fuzz=fuzz,gap_check=visual)
    assert len(calls)==calls_n
    if calls_n:assert calls[0][0] is a and calls[0][1:]==(0,gap)
    ra=record(0,gap+.8 if merge else .8,(0,0,10,10),last=gap if merge else 0)
    rb=record(gap,gap+.8,(0,0,10,10),last=gap)
    check(out,[a] if merge else [a,b],[ra] if merge else [ra,rb],inputs,[ra,rb])

@pytest.mark.parametrize('scans,merge',[
    ([],True),
    ([(.5,(0,0),[('replacement',(0,0,10,10),.6)])],True),
    ([(.5,(0,0),[('replacement',(0,0,10,10),.6)]),(.5,(0,0),[('replacement',(0,0,10,10),.6)])],False),
    ([(.5,(0,0),[('replacement',(0,0,10,10),.6),('replacement',(0,0,10,10),.6)])],False),
    ([(.5,(0,0),[('replacement',(0,0,10,10),.5999),('replacement',(0,0,10,10),.5999)])],True),
    ([(.01,(0,0),[('replacement',(0,0,10,10),.6)]),(.99,(0,0),[('replacement',(0,0,10,10),.6)])],True),
    ([(.6,(0,0),[('replacement',(0,0,10,10),.6)]),(.4,(0,0),[('different',(0,0,10,10),.6)])],True),
])
def test_unchanged_strict_contradiction_duplicate_and_unordered_scan_rules(scans,merge):
    a=det(0);b=det(1);inputs=[a,b];out=m.merge_detections(inputs,.2,scans=scans,bridge_gap=4,fuzz=fuzz)
    ra=record(0,1.2 if merge else .2,(0,0,10,10),last=1 if merge else 0)
    rb=record(1,1.2,(0,0,10,10),last=1)
    check(out,[a] if merge else [a,b],[ra] if merge else [ra,rb],inputs,[ra,rb])

def test_tail_uses_final_union_and_dense_metadata_remains_direct():
    a=det(0,off=(3,4),track=7,person=8,poly=(((.1,.2),(.3,.4)),))
    b=det(.1,(20,0,30,10));dense=det(.15,(20,0,30,10),cat='face',text='',dense=True,track=4,person=5)
    dense.t_end=.17;c=det(.2,(40,0,50,10));inputs=[a,b,dense,c]
    scans=[(.3,(0,0),[('abcdefghij',(40,0,50,10),.5)]),(.4,(0,0),[]),(.5,(0,0),[('abcdefghij',(40,0,50,10),.99)])]
    out=m.merge_detections(inputs,.8,scans=scans,fuzz=fuzz)
    ra=record(0,1.1,(0,0,50,10),off=(3,4),last=.3,track=7,person=8,poly=(((.1,.2),(.3,.4)),))
    rd=record(.15,.17,(20,0,30,10),cat='face',text='',last=.15,dense=True,track=4,person=5)
    check(out,[a,dense],[ra,rd],inputs,[ra,record(.1,.9,(20,0,30,10),last=.1),rd,record(.2,1.,(40,0,50,10),last=.2)])

def test_repeated_reference_aliases_keep_original_mutations():
    a=det(0);inputs=[a,a];out=m.merge_detections(inputs,.8,fuzz=fuzz)
    ra=record(0,.8,(0,0,10,10));check(out,[a],[ra],inputs,[ra,ra])

def test_unhashable_category_has_original_equality_semantics():
    a=det(0,cat=['email']);b=det(.1,cat=['email']);inputs=[a,b]
    out=m.merge_detections(inputs,.8,fuzz=fuzz)
    ra=record(0,.9,(0,0,10,10),cat=['email'],last=.1);rb=record(.1,.9,(0,0,10,10),cat=['email'],last=.1)
    check(out,[a],[ra],inputs,[ra,rb])

def test_malformed_box_in_unreached_geometry_remains_unreached():
    a=det(0,None);b=det(.1,cat='phone');inputs=[a,b];out=m.merge_detections(inputs,.8)
    ra=record(0,.8,None);rb=record(.1,.9,(0,0,10,10),cat='phone',last=.1)
    check(out,[a,b],[ra,rb],inputs,[ra,rb])

def test_malformed_reached_box_keeps_original_error_and_prior_mutations():
    a=det(0,None);b=det(.1);inputs=[a,b]
    with pytest.raises(TypeError,match="'NoneType' object is not subscriptable"):
        m.merge_detections(inputs,.8)
    assert vars(a)==record(0,.8,None)
    assert vars(b)==record(.1,.9,(0,0,10,10),last=.1)

@pytest.mark.parametrize('box',[(10,10,0,0),(float('inf'),0,float('inf'),10)])
def test_nonordinary_ordered_boxes_keep_original_result(box):
    a=det(0,box);out=m.merge_detections([a],.8)
    assert out==[a] and out[0] is a and vars(a)==record(0,.8,box)


def test_real_score_boundaries_are_exact():
    assert fuzz.ratio('abcdefghij','abcdefgXYZ')==70
    assert fuzz.partial_ratio('abcdefghijklmnopqrst','ZZZZZZZZZZZZZZZabcdeXghijXlmnoXqrstZZZZZZZZZZZZZZZ')==85

def test_missing_box_on_dense_input_remains_unreached():
    a=det(0,dense=True);del a.cbox
    out=m.merge_detections([a],.8)
    assert out[0] is a
    assert vars(a)=={k:v for k,v in record(0,0,(0,0,10,10),dense=True).items() if k!='cbox'}

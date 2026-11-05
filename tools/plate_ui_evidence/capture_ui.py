"""Capture the real OpenScrub UI using synthetic, manually defined reports.

No inference accuracy is asserted by these UI fixtures. This script starts the
actual Flask application and uses its actual APIs and PAGE JavaScript.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urljoin
import cv2
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
parser.add_argument('--out', required=True)
args=parser.parse_args()
ROOT=Path(args.out).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(Path(args.repo).resolve()))
import openscrub_web as web

jobs = ROOT / 'ui-fixtures/jobs'
jdir = jobs / 'synthetic-masks'
jdir.mkdir(parents=True, exist_ok=True)
video = jdir / 'input.mp4'
if not video.exists():
    frame = np.full((660, 1280, 3), (32, 27, 23), np.uint8)
    cv2.putText(frame, 'SYNTHETIC MASK REVIEW', (70, 74), cv2.FONT_HERSHEY_SIMPLEX, 1, (230, 230, 230), 2)
    quads = [np.array([[105,285],[345,225],[370,305],[130,365]],np.int32),
             np.array([[500,240],[805,278],[765,365],[515,330]],np.int32),
             np.array([[930,260],[1210,260],[1210,355],[930,355]],np.int32)]
    titles = ['Rotated outline', 'Perspective outline', 'Separate parts + hole']
    for i,(q,title) in enumerate(zip(quads,titles)):
        cv2.rectangle(frame,(60+i*420,180),(400+i*420,420),(65,60,55),-1)
        cv2.putText(frame,title,(65+i*420,145),cv2.FONT_HERSHEY_SIMPLEX,.65,(220,220,220),1)
        plate = np.full((100,300,3),235,np.uint8)
        cv2.putText(plate,'DEMO-00',(12,72),cv2.FONT_HERSHEY_SIMPLEX,1.8,(30,30,30),4)
        src=np.float32([[0,0],[299,0],[299,99],[0,99]])
        m=cv2.getPerspectiveTransform(src,q.astype(np.float32))
        warped=cv2.warpPerspective(plate,m,(1280,660))
        mask=np.zeros((660,1280),np.uint8);cv2.fillPoly(mask,[q],255)
        frame[mask>0]=warped[mask>0]
    cv2.rectangle(frame,(1050,250),(1085,365),(70,100,115),-1)
    cv2.circle(frame,(1155,305),18,(70,100,115),-1)
    cv2.putText(frame,'Imported synthetic polygons - this preview does not run a plate model.',(70,535),cv2.FONT_HERSHEY_SIMPLEX,.7,(180,180,180),1)
    cv2.imwrite(str(jdir/'source.jpg'),frame)
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(1280,660))
    for _ in range(20):writer.write(frame)
    writer.release()
    def norm(points,box):
        a,b,c,d=box
        return [[(x-a)/(c-a),(y-b)/(d-b)] for x,y in points]
    detections=[]
    for i,q in enumerate(quads):
        bx=[int(q[:,0].min()),int(q[:,1].min()),int(q[:,0].max()),int(q[:,1].max())]
        poly=[norm(q,bx)];holes=[]
        if i==2:
            poly=[norm([(930,260),(1049,260),(1049,355),(930,355)],bx),norm([(1086,260),(1210,260),(1210,355),(1086,355)],bx)]
            circle=[(1155+18*np.cos(t),305+18*np.sin(t)) for t in np.linspace(0,2*np.pi,32,endpoint=False)]
            holes=[[],[norm(circle,bx)]]
        detections.append(dict(t_start=0,t_end=1.9,cbox=bx,category='plate',text='plate',confidence=1,aoff=[0,0],last_seen=0,dense=False,track=-1,person=-1,poly=poly,poly_holes=holes,mask_pad=0,enabled=True))
    doc=dict(provenance=dict(input=str(video),original_input='synthetic-mask-review.mp4',settings=dict(pad=8,mode='box')),render_state=dict(fps=10,cum=[[0,0]]*20,bands=[[0,0]]*20),detections=detections)
    (jdir/'report.json').write_text(json.dumps(doc))

if hasattr(web.openscrub.TextRegionDetector,'find_plate'):
    from narrow_ui_fixture import make_narrow_job
    make_narrow_job(ROOT,web)

web.JOBS_DIR=str(jobs)
web.openscrub_update=None
web.rehydrate_jobs()
from werkzeug.serving import make_server
server=make_server('127.0.0.1',0,web.app,threaded=True)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
from playwright.sync_api import sync_playwright

errors=[]
dialogs=[]
checks={}
try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1100),device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
        page.goto('http://127.0.0.1:%d/'%server.server_port,wait_until='networkidle')
        checks['title']=page.title()
        if 'OpenScrub' not in checks['title']:
            raise AssertionError('Unexpected page identity: '+checks['title'])
        page.screenshot(path=str(ROOT/'scan-settings-desktop.png'),full_page=True)
        coverage=page.locator('#plateCoverage')
        if not coverage.count():
            coverage=page.locator('#plate_coverage')
        if coverage.count():
            coverage.select_option('narrow')
            page.screenshot(path=str(ROOT/'narrow-settings-desktop.png'),full_page=True)
            checks['narrow_control_value']=coverage.input_value()
            group=page.locator('#plateCoverageControls')
            if group.count():
                group.screenshot(path=str(ROOT/'narrow-controls.png'))
        page.get_by_role('link',name='synthetic-mask-review.mp4',exact=True).click()
        page.locator('#review').wait_for(state='visible')
        page.wait_for_function('SHELLPH === "review"')
        page.get_by_role('button',name='▶ Preview video & edit boxes (before rendering)',exact=True).click()
        page.locator('#beImg').wait_for(state='visible')
        page.wait_for_function('document.getElementById("beImg") && document.getElementById("beImg").naturalWidth > 0 && BE.boxes.length===3 && !BE.pending')
        checks['box_count']=page.evaluate('BE.boxes.length')
        checks['shape_contours']=page.evaluate('BE.boxes.map(x=>(x.mask_contours||[]).length)')
        page.locator('#review').screenshot(path=str(ROOT/'mask-review-desktop.png'))
        if page.evaluate('typeof beRefresh === "function"'):
            # Exercise actual pointer gestures and the actual read-only API.
            report_before=page.request.get('http://127.0.0.1:%d/api/jobs/synthetic-masks/report'%server.server_port).json()
            original=page.evaluate('BE.boxes.find(x=>x.i===2).box')
            def drag_third(dx):
                cv=page.locator('#beCv')
                cv.scroll_into_view_if_needed()
                at=cv.bounding_box()
                p=page.evaluate('(()=>{const b=BE.boxes.find(x=>x.i===2);return {x:(b.box[0]+b.box[2])/2*BE.scale,y:(b.box[1]+b.box[3])/2*BE.scale,s:BE.scale};})()')
                # The editor selects on the first click; dragging starts
                # on a subsequent pointerdown inside the selected guide.
                page.mouse.click(at['x']+p['x'],at['y']+p['y'])
                page.wait_for_function('BE.sel===2 && !BE.pending')
                page.mouse.move(at['x']+p['x'],at['y']+p['y'])
                page.mouse.down()
                assert page.evaluate('BE.drag && BE.drag.kind')=='move'
                page.mouse.move(at['x']+p['x']+dx*p['s'],at['y']+p['y'],steps=5)
                page.mouse.up()
                page.wait_for_function('!BE.pending && !BE.drag')
            drag_third(20)
            edited=page.evaluate('BE.boxes.find(x=>x.i===2)')
            assert not edited['shaped'] and len(edited['mask_contours'])==1
            assert min(p[0] for ring in edited['mask_contours'] for p in ring)<edited['box'][0]
            page.locator('#beslot').screenshot(path=str(ROOT/'edited-box-preview-desktop.png'))
            drag_third(-20)
            restored=page.evaluate('BE.boxes.find(x=>x.i===2)')
            assert restored['box']==original and restored['shaped']
            assert len(restored['mask_contours'])==3
            report_after=page.request.get('http://127.0.0.1:%d/api/jobs/synthetic-masks/report'%server.server_port).json()
            assert report_before==report_after
            page.locator('#bb2').click()
            page.wait_for_function('!BE.pending && BE.boxes.length===2')
            page.locator('#bb2').click()
            page.wait_for_function('!BE.pending && BE.boxes.length===3')
            checks['pending_edits']={'changed_box_padded':True,'return_restores_hole':True,'report_unchanged':True,'toggle_refresh':True}
        canvas=page.locator('#beCv').bounding_box()
        point=page.evaluate('({x:(BE.boxes[0].box[0]+BE.boxes[0].box[2])/2*BE.scale,y:(BE.boxes[0].box[1]+BE.boxes[0].box[3])/2*BE.scale})')
        page.mouse.click(canvas['x']+point['x'],canvas['y']+point['y'])
        checks['selected']=page.evaluate('BE.sel')
        if checks['selected']<0:
            raise AssertionError('Box selection failed')
        page.locator('#beslot').screenshot(path=str(ROOT/'selected-mask-desktop.png'))
        page.close()
        page=browser.new_page(viewport=dict(width=390,height=844),device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
        page.goto('http://127.0.0.1:%d/'%server.server_port,wait_until='networkidle')
        page.get_by_role('link',name='synthetic-mask-review.mp4',exact=True).click()
        page.locator('#review').wait_for(state='visible')
        page.wait_for_function('SHELLPH === "review"')
        page.get_by_role('button',name='▶ Preview video & edit boxes (before rendering)',exact=True).click()
        page.locator('#beImg').wait_for(state='visible')
        page.wait_for_function('document.getElementById("beImg") && document.getElementById("beImg").naturalWidth > 0 && BE.boxes.length===3 && !BE.pending')
        page.locator('#review').screenshot(path=str(ROOT/'mask-review-mobile.png'))
        checks['mobile_body_width']=page.evaluate('document.body.scrollWidth')
        checks['mobile_viewport_width']=390
        if hasattr(web.openscrub.TextRegionDetector,'find_plate'):
            page.close()
            page=browser.new_page(viewport=dict(width=1440,height=1100),device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
            page.goto('http://127.0.0.1:%d/'%server.server_port,wait_until='networkidle')
            page.get_by_role('link',name='synthetic-lettering.webm',exact=True).click()
            page.locator('#review').wait_for(state='visible')
            page.wait_for_function('SHELLPH==="review"')
            page.get_by_role('button',name='▶ Preview video & edit boxes (before rendering)',exact=True).click()
            page.wait_for_function('BE.indexed && !BE.pending && BE.imageFrame===0 && BE.maskFrame===0 && BE.boxes.length===1')
            assert page.locator('#beT').get_attribute('step')=='1'
            page.locator('#beNext').click()
            page.wait_for_function('!BE.pending && BE.imageFrame===1 && BE.maskFrame===1 && BE.boxes[0].box[0]===183')
            image=page.request.get(urljoin('http://127.0.0.1:%d/'%server.server_port,page.locator('#beImg').get_attribute('src'))).body()
            decoded=cv2.imdecode(np.frombuffer(image,np.uint8),cv2.IMREAD_COLOR)
            assert abs(float(decoded[13:23,13:23].mean())-20)<6
            page.locator('#beNext').click()
            page.wait_for_function('!BE.pending && BE.imageFrame===2 && BE.maskFrame===2 && BE.boxes[0].box[0]===186')
            page.locator('#bePrev').click()
            page.wait_for_function('!BE.pending && BE.frame===1 && BE.maskFrame===1')
            page.locator('#beT').press('End')
            page.wait_for_function('!BE.pending && BE.frame===47 && BE.maskFrame===47')
            page.locator('#review').screenshot(path=str(ROOT/'narrow-mask-review-desktop.png'))
            page.locator('#beT').press('Home')
            page.wait_for_function('!BE.pending && BE.frame===0 && BE.maskFrame===0')
            page.locator('#bePlay').click()
            try:
                page.wait_for_function('BE.playing && document.getElementById("beVid").currentTime>0',timeout=5000)
            except Exception:
                checks['playback_failure']=page.evaluate('(()=>{const v=document.getElementById("beVid");return {playing:BE.playing,time:v.currentTime,duration:v.duration,paused:v.paused,ended:v.ended,ready:v.readyState,error:v.error?{code:v.error.code,message:v.error.message}:null,canPlay:v.canPlayType("video/webm; codecs=vp9")};})()')
                checks['dialogs']=dialogs
                checks['page_errors']=errors
                (ROOT/'ui-checks.json').write_text(json.dumps(checks,indent=2))
                page.screenshot(path=str(ROOT/'playback-failure.png'))
                print(json.dumps(checks))
                raise
            assert page.evaluate('(()=>{const c=document.getElementById("beCv");return c.getContext("2d").getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===3 && v>0)})()') is False
            page.locator('#bePlay').click()
            page.wait_for_function('!BE.playing && !BE.pending && BE.imageFrame===BE.frame && BE.maskFrame===BE.frame')
            checks['indexed_review']={'fps':120,'next_previous_frames':True,'image_pixel_matches_frame':True,'end_frame':47,'playback_hides_masks':True,'pause_restores_matching_mask':True}
        checks['page_errors']=errors
        (ROOT/'ui-checks.json').write_text(json.dumps(checks,indent=2))
        if errors:
            raise AssertionError('Application JavaScript errors: '+str(errors))
        browser.close()
finally:
    server.shutdown()
print(json.dumps(checks))


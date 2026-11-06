import service
def show(r):
 w=service.WORKSHOPS[r["workshop"]]
 return {"message":"신청 완료","name":w["name"],"time":w["time"],"workshop":r["workshop"],"confirmation":r["confirmation"]}
def submit(db,request_id,member,workshop,*,online=True,lose_response=False):
 if not online:return {"message":"연결 확인 필요"}
 r=service.confirm(db,request_id,member,workshop)
 if lose_response:return {"message":"결과 확인 필요"}
 if r["code"]==200:return show(r)
 if r["code"]==409:
  old=service.status(db,request_id,member)
  if old["code"]==200 and old["workshop"]==workshop:return show(old)
 return {"message":"신청 실패","code":r["code"]}
def recover(db,request_id,member):
 r=service.status(db,request_id,member)
 if r["code"]==200:return show(r)
 return {"message":"결과 확인 필요","code":r["code"]}

from flask import Flask, request
from flask_restful import Resource, Api
import redis
from rq import Queue
import json
import time
import math
import os

app = Flask(__name__)
api = Api(app)

r = redis.Redis(host=os.environ['REDIS_URL'], port=6379)
q = Queue(connection=r)

def matcher(userid):
    if r.get(f"user:{userid}") == None:
      return False

    rooms = list(r.smembers("groups"))
    config_max_players = r.hmget("config", "max-players")[0].decode('utf-8')
    config = {
      "max-players": config_max_players
    }

    
    def createMatches():
      # try to make a match for each roster in the queue
      if not tryMakeMatch(userid):
        # move rosters we couldn't find match for to the end of the queue
        job = q.enqueue_call(func=matcher,
              args=(userid,),
              timeout=30,
              job_id=str(userid))
      
    def joinRoom(room):
      
      jroom = json.loads(r.get(room.decode('utf-8')))
      user_score = json.loads(r.get(f"user:{userid}"))["score"]
      
      suma = 0
      print(jroom["users"])
      if jroom["users"] != None:
        for i in jroom["users"]:
          suma += json.loads(r.get(f"user:{i}"))["score"]
      
      jroom["num_users"] = int(jroom["num_users"]) + 1
      
      if jroom["users"] != None: 
        jroom["users"].append(userid)
      else:
        jroom["users"] = [userid]
      
      jroom["avg_score"] = (suma + user_score) / jroom["num_users"]
      
      x = {
        "num_users": jroom["num_users"],
        "users": jroom["users"],
        "avg_score": int(jroom["avg_score"])
      }

      print(x)

      if  jroom["num_users"] >= int(config["max-players"]):
        ## Notificar que ya se tiene un grupo
        r.srem("groups", room)
        r.delete(room)
        print("Se encontró un equipo completo")
        return True

      json_res = json.dumps(x)

      r.set(room, str(json_res))

    def tryMakeMatch(target):
      # gather rosters that are good potential matches
      potentials = gatherPotentials(target)

      for room in potentials:
        size_room = size = json.loads(r.get(room).decode('utf-8'))["num_users"]
        if canJoinTeam(size_room):
          print(">> Joined in team")
          """join team"""
          joinRoom(room)
          return True

      
      
      return False

    # CO
    def gatherPotentials(target):
      rooms = list(r.smembers("groups"))
      potentials = []
      jtarget = json.loads(r.get(f"user:{target}").decode('utf-8'))
      
      if len(rooms) == 0:
        x = {
          "num_users": 0,
          "users": [],
          "avg_score": 0
        }

        json_res = json.dumps(x)

        r.incr("id_user")
        id_user = r.get("id_user")

        r.set(f"group:{id_user}", str(json_res))
        r.sadd("groups", f"group:{id_user}")
        rooms = list(r.smembers("groups"))
      
      for room in rooms:
        jroom = json.loads(r.get(room))
        
        avg_score = jroom['avg_score']
        target_score = int(jtarget['score'])
        # check conditions where rosters are never allowed to match
        #if roster.gameModes != target.gameModes:
        #  continue

        if avg_score > target_score + 100:
          continue
        if avg_score < target_score - 100:
          continue
        
        potentials.append(room)
        
        # limit choices for performance
        #if len(potentials) >= config.filter.potentials.max:
        #  break

      # return potential rooms user can join
      return potentials
      

    def canJoinTeam(size_team):
      # roster is too big for this team
      if int(size_team) + 1 > int(config["max-players"]):
        return False 
          
      # don't pick rosters that are much different size than what exists
      # if abs(len(roster) - otherTeam.maxRosterSize) > config.rosterSize.maxDiff:
      #   return False
        
      return True

    """ Function that returns len(n) and simulates a delay """

    createMatches()    

    print("Task running")
    time.sleep(2)
    print(f"Dequeue user {userid}")
    print("Task complete")

    return userid

class queue(Resource):
  def post(self):
    """ If userid is not in POST form then return 400 Bad Request """
    # if hasattr(request,'userid'):
    #   return {'error': 'userid not provided'}, 400
    try:
      userid = request.get_json()["userid"]
    except: 
      return {"error": "userid not provided"}, 400 
    """ Enqueue the user and dequeue with matcher function """
    job = q.enqueue_call(func=matcher,
              args=(userid,),
              timeout=30,
              job_id=str(userid))
    return {"userid": job.id, "enqueued_at": str(job.enqueued_at)}, 200

class create(Resource):
  def post(self):
    try:
      userid = request.get_json()["userid"]
    except: 
      return {"error": "userid not provided"}, 400 
    
    x = {
      "id": 0,
      "score": 100
    }

    json_res = json.dumps(x)

    r.set(f"user:{userid}", str(json_res))
    r.sadd("users", f"user:{userid}")
    return {"message": f"user {userid} created"}, 201

api.add_resource(queue, '/')
api.add_resource(create, '/create')

if __name__ == "__main__":
    app.run(debug=True, host= '0.0.0.0')
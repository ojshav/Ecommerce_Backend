from models.live_stream import LiveStream
from models.product import Product
from auth.models.models import MerchantProfile
from models.youtube_token import YouTubeToken
from common.database import db
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader
from services.s3_service import get_s3_service
from flask import current_app
import requests
from dateutil import parser
import pytz
import logging
from models.live_stream import StreamStatus

class MerchantLiveStreamController:
    @staticmethod
    def upload_thumbnail_to_s3(file):
        """Upload live stream thumbnail to S3"""
        try:
            s3_service = get_s3_service()
            upload_result = s3_service.upload_generic_asset(file)
            return upload_result['url'], upload_result['s3_key']
        except Exception as e:
            current_app.logger.error(f"Failed to upload live stream thumbnail to S3: {str(e)}")
            raise Exception(f"Failed to upload thumbnail: {str(e)}")
    
    @staticmethod
    def upload_thumbnail_to_cloudinary(file):
        """Legacy method - kept for backward compatibility but redirects to S3"""
        return MerchantLiveStreamController.upload_thumbnail_to_s3(file)

    @staticmethod
    def schedule_youtube_live_event(access_token, title, description, scheduled_time, return_livestream_id=False, allow_embedding=True):
        logging.debug(f"Scheduling YouTube event: title={title}, scheduled_time={scheduled_time}, allow_embedding={allow_embedding}")
        # 1. Create the broadcast
        broadcast_url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        broadcast_body = {
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": scheduled_time,
            },
            "status": {
                "privacyStatus": "public",
                "embeddable": allow_embedding
            },
            "kind": "youtube#liveBroadcast"
        }
        broadcast_resp = requests.post(broadcast_url, headers=headers, json=broadcast_body)
        logging.debug(f"Broadcast response: {broadcast_resp.status_code} {broadcast_resp.text}")
        if broadcast_resp.status_code != 200:
            raise Exception(f"YouTube API error (broadcast): {broadcast_resp.text}")
        broadcast_data = broadcast_resp.json()
        broadcast_id = broadcast_data['id']

        # 2. Create the liveStream (RTMP info)
        livestream_url = "https://www.googleapis.com/youtube/v3/liveStreams?part=snippet,cdn,contentDetails,status"
        livestream_body = {
            "snippet": {
                "title": f"Stream for {title}",
                "description": description
            },
            "cdn": {
                "frameRate": "variable",
                "ingestionType": "rtmp",
                "resolution": "variable"
            }
        }
        livestream_resp = requests.post(livestream_url, headers=headers, json=livestream_body)
        logging.debug(f"LiveStream response: {livestream_resp.status_code} {livestream_resp.text}")
        if livestream_resp.status_code != 200:
            raise Exception(f"YouTube API error (livestream): {livestream_resp.text}")
        livestream_data = livestream_resp.json()
        livestream_id = livestream_data['id']

        # 3. Bind the liveStream to the broadcast
        bind_url = f"https://www.googleapis.com/youtube/v3/liveBroadcasts/bind?id={broadcast_id}&part=id,snippet,contentDetails,status"
        bind_body = {
            "id": broadcast_id,
            "streamId": livestream_id
        }
        bind_resp = requests.post(bind_url, headers=headers, json=bind_body)
        logging.debug(f"Bind response: {bind_resp.status_code} {bind_resp.text}")
        if bind_resp.status_code != 200:
            raise Exception(f"YouTube API error (bind): {bind_resp.text}")

        # 4. Fetch the liveStream info to get the RTMP details (cdn)
        info_url = f"https://www.googleapis.com/youtube/v3/liveStreams?part=cdn&id={livestream_id}"
        info_resp = requests.get(info_url, headers=headers)
        logging.debug(f"LiveStream info GET response: {info_resp.status_code} {info_resp.text}")
        if info_resp.status_code == 200:
            info_data = info_resp.json()
            items = info_data.get('items', [])
            if items:
                cdn = items[0].get('cdn', {})
                ingestion_info = cdn.get('ingestionInfo', {})
                rtmp_info = {
                    "ingestionAddress": ingestion_info.get("ingestionAddress"),
                    "streamName": ingestion_info.get("streamName"),
                    "streamUrl": f"{ingestion_info.get('ingestionAddress')}/{ingestion_info.get('streamName')}" if ingestion_info.get("ingestionAddress") and ingestion_info.get("streamName") else None
                }
            else:
                rtmp_info = {"ingestionAddress": None, "streamName": None, "streamUrl": None}
        else:
            rtmp_info = {"ingestionAddress": None, "streamName": None, "streamUrl": None}
        logging.debug(f"RTMP info (after GET): {rtmp_info}")

        # 5. Return all info
        if return_livestream_id:
            return broadcast_id, broadcast_data['snippet'].get('liveBroadcastContent', ''), broadcast_data['snippet'].get('thumbnails', {}), rtmp_info, livestream_id
        else:
            return broadcast_id, broadcast_data['snippet'].get('liveBroadcastContent', ''), broadcast_data['snippet'].get('thumbnails', {}), rtmp_info

    @staticmethod
    def schedule_live_stream(merchant_id, title, description, product_id, scheduled_time, thumbnail_file=None, thumbnail_url=None, allow_embedding=True):
        logging.debug(f"schedule_live_stream called: merchant_id={merchant_id}, title={title}, product_id={product_id}, scheduled_time={scheduled_time}")
        # Validate product
        product = Product.query.filter_by(product_id=product_id, merchant_id=merchant_id, deleted_at=None).first()
        if not product:
            raise Exception("Product not found or not owned by merchant.")
        # Handle thumbnail
        thumbnail_public_id = None
        if thumbnail_file:
            thumbnail_url, thumbnail_public_id = MerchantLiveStreamController.upload_thumbnail_to_cloudinary(thumbnail_file)
        # Get YouTube token from DB (youtube_token.py)
        yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
        if not yt_token:
            raise Exception("No active YouTube token found for merchant.")
        access_token = yt_token.access_token  # Always use the access token from the DB
        # Convert scheduled_time to UTC RFC3339
        dt = parser.isoparse(scheduled_time)
        if dt.tzinfo is None:
            local_tz = pytz.timezone('Asia/Kolkata')  # Change as appropriate
            dt = local_tz.localize(dt)
        dt_utc = dt.astimezone(pytz.utc)
        scheduled_time_utc = dt_utc.isoformat().replace('+00:00', 'Z')
        # Schedule YouTube event and get RTMP info
        yt_event_id, yt_status, yt_thumbnails, rtmp_info, yt_livestream_id = MerchantLiveStreamController.schedule_youtube_live_event(
            access_token, title, description, scheduled_time_utc, return_livestream_id=True, allow_embedding=allow_embedding
        )
        # Save to DB
        stream = LiveStream(
            merchant_id=merchant_id,
            product_id=product_id,
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            thumbnail_public_id=thumbnail_public_id,
            scheduled_time=datetime.fromisoformat(scheduled_time),
            status='SCHEDULED',
            stream_key=yt_event_id,  # broadcast ID
            stream_url=f"https://www.youtube.com/watch?v={yt_event_id}",
            yt_livestream_id=yt_livestream_id
        )
        db.session.add(stream)
        db.session.commit()
        # Return RTMP info as well
        return stream, yt_event_id, yt_status, yt_thumbnails, rtmp_info

    @staticmethod
    def get_by_id(stream_id):
        import logging
        stream = LiveStream.get_by_id(stream_id)
        if stream:
            logging.debug(f"[get_by_id] stream_id={stream_id} stream_key={getattr(stream, 'stream_key', None)} stream_url={getattr(stream, 'stream_url', None)} yt_livestream_id={getattr(stream, 'yt_livestream_id', None)}")
            # If yt_livestream_id is present, fetch RTMP info live from YouTube
            rtmp_info = None
            if stream.yt_livestream_id:
                yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
                if yt_token:
                    access_token = yt_token.access_token
                    info_url = f"https://www.googleapis.com/youtube/v3/liveStreams?part=cdn&id={stream.yt_livestream_id}"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json"
                    }
                    info_resp = requests.get(info_url, headers=headers)
                    logging.debug(f"[get_by_id] LiveStream info GET response: {info_resp.status_code} {info_resp.text}")
                    if info_resp.status_code == 200:
                        info_data = info_resp.json()
                        items = info_data.get('items', [])
                        if items:
                            cdn = items[0].get('cdn', {})
                            ingestion_info = cdn.get('ingestionInfo', {})
                            rtmp_info = {
                                "ingestionAddress": ingestion_info.get("ingestionAddress"),
                                "streamName": ingestion_info.get("streamName"),
                                "streamUrl": f"{ingestion_info.get('ingestionAddress')}/{ingestion_info.get('streamName')}" if ingestion_info.get("ingestionAddress") and ingestion_info.get("streamName") else None
                            }
            stream.rtmp_info = rtmp_info
        return stream

    @staticmethod
    def get_by_merchant(merchant_id):
        import logging
        streams = LiveStream.get_by_merchant(merchant_id)
        for s in streams:
            logging.debug(f"[get_by_merchant] stream_id={getattr(s, 'stream_id', None)} stream_key={getattr(s, 'stream_key', None)} stream_url={getattr(s, 'stream_url', None)}")
        return streams

    @staticmethod
    def start_stream(stream, merchant_id):
        if not stream or stream.merchant_id != merchant_id:
            raise Exception("Live stream not found or not owned by merchant.")
        # 1. Transition YouTube broadcast to live
        redundant_transition = False
        if stream.stream_key and stream.yt_livestream_id:
            yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
            if yt_token:
                access_token = yt_token.access_token
                url = 'https://www.googleapis.com/youtube/v3/liveBroadcasts/transition'
                params = {
                    'broadcastStatus': 'live',
                    'id': stream.stream_key,
                    'part': 'status'
                }
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/json'
                }
                resp = requests.post(url, headers=headers, params=params)
                if resp.status_code != 200:
                    # Check for redundantTransition error
                    try:
                        err_json = resp.json()
                        errors = err_json.get('error', {}).get('errors', [])
                        if any(e.get('reason') == 'redundantTransition' for e in errors):
                            # Treat as success: already live
                            redundant_transition = True
                        else:
                            raise Exception(f'YouTube Go Live failed: {resp.text}')
                    except Exception:
                        raise Exception(f'YouTube Go Live failed: {resp.text}')
        # 2. Update local DB
        stream.is_live = True
        stream.status = 'live'
        stream.start_time = datetime.utcnow()
        db.session.commit()
        return stream

    @staticmethod
    def end_stream(stream, merchant_id):
        if not stream or stream.merchant_id != merchant_id:
            raise Exception("Live stream not found or not owned by merchant.")
        # 1. End YouTube broadcast if possible
        redundant_transition = False
        if stream.stream_key and stream.yt_livestream_id:
            yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
            if yt_token:
                access_token = yt_token.access_token
                url = 'https://www.googleapis.com/youtube/v3/liveBroadcasts/transition'
                params = {
                    'broadcastStatus': 'complete',
                    'id': stream.stream_key,
                    'part': 'status'
                }
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/json'
                }
                resp = requests.post(url, headers=headers, params=params)
                if resp.status_code != 200:
                    # Check for redundantTransition error (already ended)
                    try:
                        err_json = resp.json()
                        errors = err_json.get('error', {}).get('errors', [])
                        if any(e.get('reason') == 'redundantTransition' for e in errors):
                            # Treat as success: already ended
                            redundant_transition = True
                        else:
                            raise Exception(f'YouTube End Stream failed: {resp.text}')
                    except Exception:
                        raise Exception(f'YouTube End Stream failed: {resp.text}')
        # 2. Update local DB
        stream.is_live = False
        stream.status = 'ended'
        stream.end_time = datetime.utcnow()
        db.session.commit()
        return stream

    @staticmethod
    def delete_stream(stream, merchant_id):
        if not stream or stream.merchant_id != merchant_id:
            raise Exception("Live stream not found or not owned by merchant.")
        db.session.delete(stream)
        db.session.commit()
        return None

    @staticmethod
    def get_youtube_scheduled_streams(yt_token):
        """
        Fetch scheduled (upcoming) live broadcasts from YouTube for the merchant.
        """
        url = "https://www.googleapis.com/youtube/v3/liveBroadcasts"
        params = {
            "part": "id,snippet,contentDetails,status",
            "broadcastStatus": "upcoming",
            "maxResults": 10
        }
        headers = {
            "Authorization": f"Bearer {yt_token.access_token}",
            "Accept": "application/json"
        }
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise Exception(f"YouTube API error: {resp.text}")
        return resp.json().get("items", [])

    @staticmethod
    def get_youtube_stream_info(yt_token, stream_id):
        """
        Fetch the RTMP stream key and ingestion URL for a given YouTube stream.
        """
        url = "https://www.googleapis.com/youtube/v3/liveStreams"
        params = {
            "part": "cdn,status",
            "id": stream_id
        }
        headers = {
            "Authorization": f"Bearer {yt_token.access_token}",
            "Accept": "application/json"
        }
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise Exception(f"YouTube API error: {resp.text}")
        items = resp.json().get("items", [])
        if not items:
            return None
        cdn = items[0].get("cdn", {})
        ingestion_info = cdn.get('ingestionInfo', {})
        return {
            "ingestionAddress": ingestion_info.get("ingestionAddress"),
            "streamName": ingestion_info.get("streamName"),
            "streamUrl": f"{ingestion_info.get('ingestionAddress')}/{ingestion_info.get('streamName')}" if ingestion_info.get("ingestionAddress") and ingestion_info.get("streamName") else None
        }

    @staticmethod
    def get_merchant_youtube_scheduled_streams(merchant_id):
        yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
        if not yt_token:
            raise Exception("No active YouTube token found for merchant.")
        broadcasts = MerchantLiveStreamController.get_youtube_scheduled_streams(yt_token)
        result = []
        for b in broadcasts:
            stream_info = None
            bound_stream_id = b.get("contentDetails", {}).get("boundStreamId")
            if bound_stream_id:
                stream_info = MerchantLiveStreamController.get_youtube_stream_info(yt_token, bound_stream_id)
            result.append({
                "broadcast_id": b.get("id"),
                "title": b.get("snippet", {}).get("title"),
                "description": b.get("snippet", {}).get("description"),
                "scheduled_start_time": b.get("snippet", {}).get("scheduledStartTime"),
                "status": b.get("status", {}).get("lifeCycleStatus"),
                "stream_info": stream_info
            })
        return result

    @staticmethod
    def get_scheduled_streams_by_merchant(merchant_id):
        """
        Return all scheduled (not live, ended, or cancelled) live streams for a given merchant from the LiveStream model.
        """
        scheduled_streams = LiveStream.query.filter_by(merchant_id=merchant_id, status='scheduled', deleted_at=None).all()
        return scheduled_streams

    @staticmethod
    def get_all_streams_by_merchant(merchant_id):
        """
        Return all streams (scheduled, live, and ended) for a merchant, ordered by scheduled_time desc
        """
        streams = LiveStream.query.filter_by(
            merchant_id=merchant_id,
            deleted_at=None
        ).order_by(
            LiveStream.scheduled_time.desc()
        ).all()

        # Group streams by status
        result = {
            'scheduled': [],
            'live': [],
            'ended': []
        }

        for stream in streams:
            if stream.status == StreamStatus.scheduled:
                result['scheduled'].append(stream)
            elif stream.status == StreamStatus.live:
                result['live'].append(stream)
            elif stream.status == StreamStatus.ended:
                result['ended'].append(stream)

        return result 

    @staticmethod
    def update_stream_embedding(stream, merchant_id, allow_embedding):
        """
        Update the embedding settings for an existing live stream.
        """
        if not stream or stream.merchant_id != merchant_id:
            raise Exception("Live stream not found or not owned by merchant.")
        
        if not stream.stream_key:
            raise Exception("Stream key not found for this live stream.")
        
        yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
        if not yt_token:
            raise Exception("No active YouTube token found.")
        
        access_token = yt_token.access_token
        
        # Update the broadcast embedding settings
        url = f"https://www.googleapis.com/youtube/v3/liveBroadcasts?part=status&id={stream.stream_key}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        body = {
            "id": stream.stream_key,
            "status": {
                "embeddable": allow_embedding
            }
        }
        
        resp = requests.put(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise Exception(f"YouTube API error updating embedding: {resp.text}")
        
        return stream

    @staticmethod
    def get_available_time_slots(date_str, slot_start="09:00", slot_end="22:00"):
        """
        Returns a list of available 1-hour time slots for the given date (YYYY-MM-DD).
        Excludes slots already booked by any merchant.
        """
        # 1. Generate all possible 1-hour slots
        slots = []
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        start_hour = int(slot_start.split(":")[0])
        end_hour = int(slot_end.split(":")[0])
        for hour in range(start_hour, end_hour):
            slot_time = f"{hour:02d}:00"
            slots.append(slot_time)

        # 2. Query all booked slots for this date
        day_start = datetime.combine(date_obj, datetime.min.time())
        day_end = datetime.combine(date_obj, datetime.max.time())
        booked_streams = LiveStream.query.filter(
            LiveStream.scheduled_time >= day_start,
            LiveStream.scheduled_time <= day_end,
            LiveStream.deleted_at == None
        ).all()
        booked_slots = set()
        for stream in booked_streams:
            booked_slots.add(stream.scheduled_time.strftime("%H:%M"))

        # 3. Remove booked slots
        available_slots = [slot for slot in slots if slot not in booked_slots]
        return available_slots 
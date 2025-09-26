
# home/middleware.py
import datetime
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils.dateparse import parse_datetime

class AutoLogoutMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return

        now = datetime.datetime.now()
        last_activity_str = request.session.get('last_activity')

        if last_activity_str:
            last_activity = parse_datetime(last_activity_str)
            if last_activity:
                delta = now - last_activity
                if delta.total_seconds() > settings.SESSION_COOKIE_AGE:
                    # Logout user if session has expired
                    from django.contrib.auth import logout
                    logout(request)
                    request.session.flush()
                    return

        # Update last activity timestamp
        request.session['last_activity'] = now.isoformat()

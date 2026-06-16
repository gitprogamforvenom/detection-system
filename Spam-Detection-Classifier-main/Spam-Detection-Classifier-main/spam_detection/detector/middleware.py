class UserHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.META.get('HTTP_X_USER_ID')
        role = request.META.get('HTTP_X_USER_ROLE')
        username = request.META.get('HTTP_X_USER_USERNAME')
        
        request.authenticated_user_id = int(user_id) if user_id else None
        request.authenticated_user_role = role if role else 'analyst'
        request.authenticated_username = username if username else ''
        
        return self.get_response(request)

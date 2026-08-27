from flask import jsonify


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        return jsonify(error=err.message), err.status_code

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify(error="Not found"), 404

    @app.errorhandler(500)
    def handle_500(err):
        app.logger.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500

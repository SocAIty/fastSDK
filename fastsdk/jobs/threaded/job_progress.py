class JobProgress:
    def __init__(self, progress: float = 0, message: str = None):
        """
        Used to display _progress of a job while executing.
        :param progress: value between 0 and 1.0
        :param message: message to deliver to client.
        """
        self._progress = progress
        self._message = message

    def set_progress(self, progress: float, message: str = None):
        self._progress = progress
        self._message = message

    def get_progress(self):
        return self._progress, self._message

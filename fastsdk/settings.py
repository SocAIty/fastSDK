from singleton_decorator import singleton
from fastsdk.service_management import ServiceManager as sm
from fastsdk.service_interaction import ApiJobManager as ajm


@singleton
class _Global:
    def __init__(self):
        self._service_manager = None
        self._api_job_manager = None

    @property
    def service_manager(self) -> sm:
        if self._service_manager is None:
            self._service_manager = sm()
        return self._service_manager

    @service_manager.setter
    def service_manager(self, value: sm):
        self._service_manager = value
        self._api_job_manager.service_manager = value

    @property
    def api_job_manager(self) -> ajm:
        if self._api_job_manager is None:
            self._api_job_manager = ajm(self.service_manager)
        return self._api_job_manager

    @api_job_manager.setter
    def api_job_manager(self, value: ajm):
        self._api_job_manager = value


Global = _Global()
ServiceManager: sm = Global.service_manager
ApiJobManager: ajm = Global.api_job_manager

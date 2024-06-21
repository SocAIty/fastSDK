from typing import Union

from fastsdk.definitions.enums import ModelDomainTag, ModelTag


class AIModelDescription:
    def __init__(
            self,
            model_name: str = None,
            model_domain_tags: Union[list[str], list[ModelDomainTag], str] = None,
            model_tags: Union[list[str], list[ModelTag], str, ModelTag] = None,
            model_description: str = None,
            model_version: str = None
    ):

        self.model_name = model_name
        self.model_version = model_version
        self.model_description = model_description

        # Model domain tags
        if model_domain_tags is None:
            self.model_domain_tags = [ModelDomainTag.OTHER]
        elif isinstance(model_domain_tags, str):
            self.model_domain_tags = [ModelDomainTag(model_domain_tags)]
        elif isinstance(model_domain_tags, list):
            self.model_domain_tags = [ModelDomainTag(tag) if isinstance(tag, str) else tag for tag in model_domain_tags]

        # Model tags
        if model_tags is None:
            self.model_tags = [ModelTag.OTHER]
        elif isinstance(model_tags, str):
            self.model_tags = [ModelTag(model_tags)]
        elif isinstance(model_tags, list):
            self.model_tags = [ModelTag(tag) if isinstance(tag, str) else tag for tag in model_tags]



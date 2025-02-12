from typing import Union

from fastsdk.definitions.enums import ModelDomainTag


class AIModelDescription:
    def __init__(
            self,
            model_name: str = None,
            model_domain_tags: Union[list[str], list[ModelDomainTag], str] = None,
            model_tags: Union[list[str], str] = None,
            model_description: str = None,
            model_version: str = None,
            github_url: str = None,
            paper_url: str = None
    ):
        """
        The model description is used to find and categorize models better.
        :param model_name: The name of the model
        :param model_domain_tags: Which kind of input and output the model has. Can be a list of strings or ModelDomainTag
        :param model_tags: Arbitrary user defined tags for the model.
        :param model_description: A description of the model.
        :param model_version: The version of the model
        :param github_url: The github url of the model
        :param paper_url: The paper url of the model
        """
        self.model_name = model_name
        self.model_version = model_version
        self.model_description = model_description

        # Model domain tags
        if model_domain_tags is None:
            self.model_domain_tags = [ModelDomainTag.MISC]
        elif isinstance(model_domain_tags, str):
            self.model_domain_tags = [ModelDomainTag(model_domain_tags)]
        elif isinstance(model_domain_tags, list):
            self.model_domain_tags = [ModelDomainTag(tag) if isinstance(tag, str) else tag for tag in model_domain_tags]

        self.model_tags = model_tags
        self.github_url = github_url
        self.paper_url = paper_url


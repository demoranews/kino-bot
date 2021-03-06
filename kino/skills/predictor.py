
from sklearn.neighbors import KNeighborsClassifier

from ..functions import Functions
from ..functions import FunctionRunner

from ..slack.resource import MsgResource
from ..slack.slackbot import SlackerAdapter

from ..utils.data_loader import SkillDataLoader
from ..utils.data_loader import SkillData
from ..utils.classes import Skill


class Predictor(object):
    def __init__(self, n_neighbors=8, slackbot=None):
        self.knn = KNeighborsClassifier(n_neighbors=n_neighbors, weights="distance")

        skill_data = SkillData()
        data_X, data_y = SkillDataLoader().make_data_set(skill_data.q)
        self.knn.fit(data_X, data_y)

        if slackbot is None:
            self.slackbot = SlackerAdapter()
        else:
            self.slackbot = slackbot

    def predict_skill(self):
        data_loader = SkillDataLoader()
        test_x = data_loader.make_X()

        predict = self.knn.predict(test_x)[0]
        confidence = max(self.knn.predict_proba(test_x)[0])
        description = " ".join(Skill.classes[predict][0])
        func_name = Skill.classes[predict][1]

        if confidence >= 0.85:
            runner = FunctionRunner()
            params = runner.filter_f_params(description, func_name)

            self.slackbot.send_message(
                text=MsgResource.PREDICT_RESULT(description=description)
            )
            runner.load_function(func_name=func_name, params=params, day_of_week=[0])
        else:
            functions = Functions(self.slackbot)
            functions.remind_idea()

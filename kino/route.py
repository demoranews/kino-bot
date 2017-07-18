
import json

from .functions import Functions
from .functions import FunctionRunner
from .webhook import Webhook

from .dialog.dialog_manager import DialogManager
from .dialog.dnd import DoNotDisturbManager
from .dialog.presence import PreseneManager

from .nlp.disintegrator import Disintegrator
from .nlp.ner import NamedEntitiyRecognizer

from .notifier.between import Between
from .notifier.scheduler import Scheduler
from .notifier.skill_list import SkillList

from .kino.help import Guide
from .kino.worker import Worker

from .slack.resource import MsgResource
from .slack.slackbot import SlackerAdapter

from .skills.question import AttentionQuestion
from .skills.question import HappyQuestion

from .utils.config import Config
from .utils.data_loader import DataLoader
from .utils.data_loader import SkillData
from .utils.logger import Logger
from .utils.logger import MessageLogger
from .utils.state import State


class MsgRouter(object):

    def __init__(self):
        self.config = Config()
        self.logger = Logger().get_logger()
        self.msg_logger = MessageLogger().get_logger()

        self.dialog_manager = DialogManager()
        self.presence_manager = PreseneManager()
        self.dnd_manager = DoNotDisturbManager()

        self.f_runner = FunctionRunner()

    def preprocessing(self, text):
        self.text = text

        disintegrator = Disintegrator(text)
        self.parsed_text = disintegrator.convert2simple() + " " + text

        self.logger.info("parsed input: " + self.parsed_text)

    def route(
            self,
            text=None,
            user=None,
            channel=None,
            direct=False,
            webhook=False,
            presence=None,
            dnd=None,
            predict=False):

        if text is not None:
            self.msg_logger.info(json.dumps({"channel": channel, "user": user, "text": text}))
            self.preprocessing(text)

        if self.config.bot["ONLY_DIRECT"] is True and direct is False:
            # Skip
            return

        self.slackbot = SlackerAdapter(
            channel=channel, input_text=text, user=user)

        ner = NamedEntitiyRecognizer()

        # predict next action
        if predict:
            # Check - skills
            skill_keywords = {k: v['keyword'] for k, v in ner.skills.items()}
            func_name = ner.parse(skill_keywords, self.parsed_text)
            if func_name is not None:
                self.__call_skills(func_name)
                return

        # slack - active/away
        if presence:
            self.presence_manager.check_wake_up(presence)
            self.presence_manager.check_flow(presence)
            self.presence_manager.check_predictor(presence)

            State().presence_log(presence)
            self.logger.info("presence: " + str(presence))
            return

        # Do not disturb
        if dnd:
            self.dnd_manager.call_is_holiday(dnd)
            return

        # incomming-webhook
        if webhook:
            self.__on_relay(text)
            return

        # Check Flow
        if self.dialog_manager.is_on_flow():
            self.__on_flow()
            return

        # Check Memory
        if self.dialog_manager.is_on_memory() \
                and self.dialog_manager.is_call_repeat_skill(self.text):
            self.__on_memory()
            return

        # Check - help
        if self.dialog_manager.is_call_help(self.parsed_text):
            self.__call_help()
            return

        # Check - CRUD (Worker, Schedule, Between, FunctionManager)
        kino_keywords = {k: v['keyword'] for k, v in ner.kino.items()}
        classname = ner.parse(kino_keywords, self.parsed_text)

        if classname is not None:
            self.__call_CRUD(ner, classname)
            return

        # Check - skills
        skill_keywords = {k: v['keyword'] for k, v in ner.skills.items()}
        func_name = ner.parse(skill_keywords, self.parsed_text)
        if func_name is not None:
            self.__call_skills(func_name)
            self.__memory_predictor_skills()
            return

        self.logger.info("not understanding")
        self.slackbot.send_message(text=MsgResource.NOT_UNDERSTANDING)
        return

    def __on_relay(self, text):
        webhook = Webhook()
        webhook.relay(text)

    def __on_flow(self):
        route_class, behave, step_num = self.dialog_manager.get_flow(
            global_namespace=globals())
        self.logger.info(
            "From Flow - route to: " +
            route_class.__class__.__name__ +
            ", " +
            str(behave))
        getattr(
            route_class(
                slackbot=self.slackbot),
            behave)(
            step=step_num,
            params=self.text)

    def __on_memory(self):
        route_class, func_name, params = self.dialog_manager.get_memory(
            global_namespace=globals())
        self.logger.info(
            "From Memory - route to: " +
            route_class.__class__.__name__ +
            ", " +
            str(func_name))
        f_params = self.f_runner.filter_f_params(self.parsed_text, func_name)
        if not f_params == {}:
            params = f_params
        getattr(route_class, func_name)(**params)

    def __call_help(self):
        route_class = Guide(self.slackbot)
        behave = "help"
        self.logger.info(
            "route to: " +
            route_class.__class__.__name__ +
            ", " +
            str(behave))
        getattr(route_class, behave)()

    def __call_CRUD(self, ner, classname):
        route_class = globals()[classname](
            text=self.text, slackbot=self.slackbot)
        behave_ner = ner.kino[classname]['behave']
        behave = ner.parse(behave_ner, self.parsed_text)

        self.logger.info(
            "route to: " +
            route_class.__class__.__name__ +
            ", " +
            str(behave))
        getattr(route_class, behave)()

    def __call_skills(self, func_name):
        if self.dialog_manager.is_toggl_timer(func_name):
            f_params = {
                "description": self.text[self.text.index("toggl") + 5:]}
        else:
            f_params = self.f_runner.filter_f_params(
                self.parsed_text, func_name)

        state = State()
        state.memory_skill(self.text, func_name, f_params)
        self.logger.info(
            "From call skills - route to: " +
            func_name +
            ", " +
            str(f_params))
        getattr(Functions(slackbot=self.slackbot), func_name)(**f_params)

    def __memory_predictor_skills(self):
        data_loader = DataLoader()
        X = data_loader.make_X()[0]
        y = data_loader.make_y(self.text)
        if y is not None:
            print('in')
            skill_data = SkillData()
            skill_data.q.put_nowait((X, y))

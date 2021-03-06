import datetime

from django.views import View

from Base.Netease import NetEase
from Base.error import Error
from Base.response import error_response, response, Ret
from Base.user_validator import require_login, require_consider
from Base.validator import require_post, require_get, require_put, require_path
from Message.models import Message
from Music.models import Music, DailyRecommend


class MusicView(View):
    @staticmethod
    @require_get([('user_id', None, None)])
    @require_login
    @require_path('/api/music/list')
    def get(request):
        """ GET /api/music/list?user_id

        获取用户推荐的音乐列表
        如果user_id为空，则返回自己的数据
        """
        user_id = request.d.user_id

        o_user = request.user
        if user_id:
            musics = Music.get_list_by_user(user_id)
        else:
            musics = Music.get_list_by_user(o_user.str_id)

        music_list = []
        for o_music in musics:
            music_list.append(o_music.to_dict())

        return response(music_list)

    @staticmethod
    @require_post(['url'])
    @require_login
    @require_path('/api/music/recommend')
    def post(request):
        """ POST /api/music/recommend

        用户推荐歌曲
        """
        url = request.d.url

        o_user = request.user

        ret = NetEase.grab_music_info(url)

        if ret.error is not Error.OK:
            return error_response(ret)

        data = ret.body
        name = data['name']
        singer = data['singer']
        cover = data['cover']
        total_comment = data['total_comment']
        netease_id = data['netease_id']

        if total_comment > 999:
            return error_response(Error.COMMENT_TOO_MUCH)

        ret = Music.create(name, singer, cover, total_comment, netease_id, o_user)
        if ret.error is not Error.OK:
            return error_response(ret)
        o_music = ret.body
        if not isinstance(o_music, Music):
            return error_response(Error.STRANGE)

        return response(o_music.to_dict())

    @staticmethod
    @require_path('/api/music/update')
    def put(request):
        """ GET /api/music/update

        更新歌曲总评论数
        """
        crt_time = datetime.datetime.now().timestamp()
        for o_music in Music.objects.all():
            if crt_time - o_music.last_update_time < 60 * 60 * 12:
                continue
            ret = NetEase.get_comment(o_music.netease_id)
            if ret.error is Error.OK:
                total_comment = ret.body
                o_music.update_comment(total_comment)
        return response()


# class MusicListView(View):
#     # /api/music/list
#     @staticmethod
#     @require_get([{
#         'value': 'end',
#         'default': True,
#         'default_value': -1,
#         'process': int,
#     }, {
#         'value': 'count',
#         'default': True,
#         'default_value': 10,
#         'process': int,
#     }])
#     def get(request):
#         end = request.d.end
#         count = request.d.count
#
#         ret = Music.get_music_list(end, count)
#         if ret.error is not Error.OK:
#             return error_response(ret)
#
#         return response(ret.body)

class ConsiderView(View):
    @staticmethod
    @require_get([{
        'value': 'start',
        'process': int,
    }, {
        'value': 'count',
        'process': int,
    }])
    @require_consider
    def get(request):
        start = request.d.start
        count = request.d.count

        return response(Music.get_consider_list(start, count))

    @staticmethod
    @require_put([
        'netease_id',
        {
            'value': 'accept',
            'process': bool,
        },
        ('reason', None, ''),
    ])
    @require_consider
    def put(request):
        """ PUT /api/music/consider

        审核员审核歌曲能否进入日推
        """
        netease_id = request.d.netease_id
        accept = request.d.accept
        reason = request.d.reason

        ret = Music.get_music_by_netease_id(netease_id)
        if ret.error is not Error.OK:
            return error_response(ret)
        o_music = ret.body
        if not isinstance(o_music, Music):
            return error_response(Error.STRANGE)

        o_user = request.user
        ret = o_music.update_status(accept, o_user)

        if ret.error is not Error.OK:
            return error_response(ret)

        if accept:
            ret = DailyRecommend.push(o_music)
            if ret.error is not Error.OK:
                Message.create(
                    Message.TYPE_TABLE[Message.TYPE_PUSH_DAILY_FAIL][1] % o_music.name,
                    o_music,
                    o_user,
                    Message.TYPE_PUSH_DAILY_FAIL,
                )
                return error_response(Error.DAILY_RECOMMEND_FAILED)
            o_dr = ret.body
            if not isinstance(o_dr, DailyRecommend):
                return error_response(Error.STRANGE)
            ret = Message.create(
                Message.TYPE_TABLE[Message.TYPE_RECOMMEND_ACCEPT][1] % (
                    o_music.name,
                    o_dr.get_readable_date()
                ),
                o_music,
                o_music.re_user,
                Message.TYPE_RECOMMEND_ACCEPT,
            )
            if ret.error is not Error.OK:
                print(ret.error.eid, ret.error.msg)
        else:
            Message.create(
                Message.TYPE_TABLE[Message.TYPE_RECOMMEND_REFUSE][1] % (o_music.name, reason or '空'),
                o_music,
                o_music.re_user,
                Message.TYPE_RECOMMEND_REFUSE,
            )

        return error_response(ret)


def validate_end_date(end_date):
    if not end_date:
        return Ret()
    try:
        datetime.datetime.strptime(end_date, '%Y-%m-%d')
    except:
        return Ret(Error.END_DATE_FORMAT_ERROR)
    return Ret()


class DailyView(View):
    @staticmethod
    @require_get([
        ('end_date', validate_end_date, None),
        {
            'value': 'count',
            'process': int,
        }
    ])
    def get(request):
        end_date = request.d.end_date
        count = request.d.count

        ret = DailyRecommend.get_daily_music_list(end_date, count)
        if ret.error is not Error.OK:
            return error_response(ret)
        return response(ret.body)

import json
import os
import asyncio
import socket
import logging

from tornado import websocket, web, ioloop, escape

import shure
import config
import discover
import offline
import pco


# https://stackoverflow.com/questions/5899497/checking-file-extension
def file_list(extension):
    files = []
    dir_list = os.listdir(config.gif_dir)
    # print(fileList)
    for file in dir_list:
        if file.lower().endswith(extension):
            files.append(file)
    return files

# Its not efficecent to get the IP each time, but for now we'll assume server might have dynamic IP
def localURL():
    if 'local_url' in config.config_tree:
        return config.config_tree['local_url']
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return 'http://{}:{}'.format(ip, config.config_tree['port'])
    except:
        return 'https://micboard.io'
    return 'https://micboard.io'

def micboard_json(network_devices):
    offline_devices = offline.offline_json()
    data = []
    discovered = []
    for net_device in network_devices:
        data.append(net_device.net_json())

    if offline_devices:
        data.append(offline_devices)

    gifs = file_list('.gif')
    jpgs = file_list('.jpg')
    mp4s = file_list('.mp4')
    url = localURL()

    for device in discover.time_filterd_discovered_list():
        discovered.append(device)

    return json.dumps({
        'receivers': data, 'url': url, 'gif': gifs, 'jpg': jpgs, 'mp4': mp4s,
        'config': config.config_tree, 'discovered': discovered
    }, sort_keys=True, indent=4)

class IndexHandler(web.RequestHandler):
    def get(self):
        self.render(config.app_dir('demo.html'))

class AboutHandler(web.RequestHandler):
    def get(self):
        self.render(config.app_dir('static/about.html'))

class JsonHandler(web.RequestHandler):
    def get(self):
        self.set_header('Content-Type', 'application/json')
        self.write(micboard_json(shure.NetworkDevices))

class SocketHandler(websocket.WebSocketHandler):
    clients = set()

    def check_origin(self, origin):
        return True

    def open(self):
        self.clients.add(self)

    def on_close(self):
        self.clients.remove(self)

    @classmethod
    def close_all_ws(cls):
        for c in cls.clients:
            c.close()

    @classmethod
    def broadcast(cls, data):
        for c in cls.clients:
            try:
                c.write_message(data)
            except:
                logging.warning("WS Error")

    @classmethod
    def ws_dump(cls):
        out = {}
        if shure.chart_update_list:
            out['chart-update'] = shure.chart_update_list

        if shure.data_update_list:
            out['data-update'] = []
            for ch in shure.data_update_list:
                out['data-update'].append(ch.ch_json_mini())

        if config.group_update_list:
            out['group-update'] = config.group_update_list

        if out:
            data = json.dumps(out)
            cls.broadcast(data)
        del shure.chart_update_list[:]
        del shure.data_update_list[:]
        del config.group_update_list[:]

class SlotHandler(web.RequestHandler):
    def get(self):
        self.write("hi - slot")

    def post(self):
        data = json.loads(self.request.body)
        self.write('{}')
        for slot_update in data:
            config.update_slot(slot_update)
            print(slot_update)

class ConfigHandler(web.RequestHandler):
    def get(self):
        self.write("hi - slot")

    def post(self):
        data = json.loads(self.request.body)
        print(data)
        self.write('{}')
        config.reconfig(data)

class GroupUpdateHandler(web.RequestHandler):
    def get(self):
        self.write("hi - group")

    def post(self):
        data = json.loads(self.request.body)
        config.update_group(data)
        print(data)
        self.write(data)

class MicboardReloadConfigHandler(web.RequestHandler):
    def post(self):
        print("RECONFIG")
        config.reconfig()
        self.write("restarting")


# --------------------------------------------------------------------------- #
# Planning Center Online (PCO) integration
#
# Credentials never travel through these responses. The backend holds the secret
# (in pco.env) and only ever returns PCO data or the non-secret mapping config.
# --------------------------------------------------------------------------- #

class PcoCredentialsHandler(web.RequestHandler):
    def post(self):
        data = json.loads(self.request.body)
        app_id = (data.get('app_id') or '').strip()
        secret = (data.get('secret') or '').strip()
        if not app_id or not secret:
            self.set_status(400)
            self.write({'error': 'app_id and secret are required'})
            return
        pco.save_credentials(app_id, secret)
        pco.maybe_start_poller()
        self.write({'configured': True})


class PcoStatusHandler(web.RequestHandler):
    def get(self):
        self.write(pco.status())


class PcoMappingsHandler(web.RequestHandler):
    def post(self):
        data = json.loads(self.request.body)
        self.write(pco.save_config(data))


class PcoServiceTypesHandler(web.RequestHandler):
    async def get(self):
        try:
            self.write({'service_types': await pco.get_service_types()})
        except pco.PCOError as err:
            self.set_status(err.code)
            self.write({'error': err.message})
        except Exception as err:  # noqa: BLE001 — never leak a raw 500 to the client
            logging.exception('PCO request failed')
            self.set_status(502)
            self.write({'error': 'Planning Center request failed: {}'.format(err)})


class PcoTeamsHandler(web.RequestHandler):
    async def get(self):
        service_type_id = self.get_argument('service_type_id', None)
        if not service_type_id:
            self.set_status(400)
            self.write({'error': 'service_type_id is required'})
            return
        try:
            self.write({'teams': await pco.get_teams(service_type_id)})
        except pco.PCOError as err:
            self.set_status(err.code)
            self.write({'error': err.message})
        except Exception as err:  # noqa: BLE001 — never leak a raw 500 to the client
            logging.exception('PCO request failed')
            self.set_status(502)
            self.write({'error': 'Planning Center request failed: {}'.format(err)})


class PcoPlansHandler(web.RequestHandler):
    async def get(self):
        service_type_id = self.get_argument('service_type_id', None)
        if not service_type_id:
            self.set_status(400)
            self.write({'error': 'service_type_id is required'})
            return
        try:
            self.write({'plans': await pco.get_plans(service_type_id)})
        except pco.PCOError as err:
            self.set_status(err.code)
            self.write({'error': err.message})
        except Exception as err:  # noqa: BLE001 — never leak a raw 500 to the client
            logging.exception('PCO request failed')
            self.set_status(502)
            self.write({'error': 'Planning Center request failed: {}'.format(err)})


class PcoRosterHandler(web.RequestHandler):
    async def get(self):
        pco_cfg = config.config_tree.get('pco') or {}
        service_type_id = self.get_argument('service_type_id', None) or pco_cfg.get('service_type_id')
        plan_id = self.get_argument('plan_id', None)
        if not service_type_id:
            self.set_status(400)
            self.write({'error': 'service_type_id is required'})
            return
        try:
            if not plan_id:
                plan = await pco.get_next_plan(service_type_id)
                if not plan:
                    self.write({'plan_id': None, 'roster': []})
                    return
                plan_id = plan['id']
            self.write({'plan_id': plan_id, 'roster': await pco.get_roster(service_type_id, plan_id)})
        except pco.PCOError as err:
            self.set_status(err.code)
            self.write({'error': err.message})
        except Exception as err:  # noqa: BLE001 — never leak a raw 500 to the client
            logging.exception('PCO request failed')
            self.set_status(502)
            self.write({'error': 'Planning Center request failed: {}'.format(err)})


class PcoSyncHandler(web.RequestHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
        except ValueError:
            data = {}
        try:
            self.write(await pco.sync(data.get('plan_id')))
        except pco.PCOError as err:
            self.set_status(err.code)
            self.write({'error': err.message})
        except Exception as err:  # noqa: BLE001 — never leak a raw 500 to the client
            logging.exception('PCO request failed')
            self.set_status(502)
            self.write({'error': 'Planning Center request failed: {}'.format(err)})



# https://stackoverflow.com/questions/12031007/disable-static-file-caching-in-tornado
class NoCacheHandler(web.StaticFileHandler):
    def set_extra_headers(self, path):
        # Disable cache
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')


def twisted():
    app = web.Application([
        (r'/', IndexHandler),
        (r'/about', AboutHandler),
        (r'/ws', SocketHandler),
        (r'/data.json', JsonHandler),
        (r'/api/group', GroupUpdateHandler),
        (r'/api/slot', SlotHandler),
        (r'/api/config', ConfigHandler),
        (r'/api/pco/credentials', PcoCredentialsHandler),
        (r'/api/pco/status', PcoStatusHandler),
        (r'/api/pco/mappings', PcoMappingsHandler),
        (r'/api/pco/service_types', PcoServiceTypesHandler),
        (r'/api/pco/teams', PcoTeamsHandler),
        (r'/api/pco/plans', PcoPlansHandler),
        (r'/api/pco/roster', PcoRosterHandler),
        (r'/api/pco/sync', PcoSyncHandler),
        # (r'/restart/', MicboardReloadConfigHandler),
        (r'/static/(.*)', web.StaticFileHandler, {'path': config.app_dir('static')}),
        (r'/bg/(.*)', NoCacheHandler, {'path': config.get_gif_dir()})
    ])
    # https://github.com/tornadoweb/tornado/issues/2308
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.listen(config.web_port())
    ioloop.PeriodicCallback(SocketHandler.ws_dump, 50).start()
    pco.maybe_start_poller()
    ioloop.IOLoop.instance().start()

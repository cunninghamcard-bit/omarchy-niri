"""Run in a disposable desktop and select a display in the portal dialog.

Diagnostic for GStreamer/PipeWire compatibility. This is not a release gate:
Niri DMA-BUF streams may not negotiate with pipewire-gstreamer even when
browser WebRTC sharing works.
Requires Python GObject and GStreamer pipewiresrc in the test environment.
"""
import os
import uuid
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst
Gst.init(None)

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
service = 'org.freedesktop.portal.Desktop'
portal = '/org/freedesktop/portal/desktop'
interface = 'org.freedesktop.portal.ScreenCast'
loop = GLib.MainLoop()

def request(method, signature, args):
  token = 'niriqa' + uuid.uuid4().hex
  options = args[-1]
  options['handle_token'] = GLib.Variant('s', token)
  path = '/org/freedesktop/portal/desktop/request/' + bus.get_unique_name()[1:].replace('.', '_') + '/' + token
  result = []
  def response(*values):
    result.append(values[-2].unpack())
    loop.quit()
  subscription = bus.signal_subscribe(service, 'org.freedesktop.portal.Request', 'Response', path, None, Gio.DBusSignalFlags.NONE, response, None)
  bus.call_sync(service, portal, interface, method, GLib.Variant(signature, args), None, Gio.DBusCallFlags.NONE, -1, None)
  timeout = GLib.timeout_add_seconds(120, lambda: (loop.quit(), False)[1])
  loop.run()
  if result: GLib.source_remove(timeout)
  bus.signal_unsubscribe(subscription)
  assert result and result[0][0] == 0, (method, result)
  print('PASS:', method, result[0][1], flush=True)
  return result[0][1]

session = request('CreateSession', '(a{sv})', ({'session_handle_token': GLib.Variant('s', 'session' + uuid.uuid4().hex)},))['session_handle']
try:
  request('SelectSources', '(oa{sv})', (session, {'types': GLib.Variant('u', 1), 'multiple': GLib.Variant('b', False)}))
  selected = request('Start', '(osa{sv})', (session, '', {}))
  node, properties = selected['streams'][0]
  serial = properties.get('pipewire-serial')
  target = 'target-object=' + str(serial) if serial is not None else 'path=' + str(node)
  reply, fds = bus.call_with_unix_fd_list_sync(service, portal, interface, 'OpenPipeWireRemote', GLib.Variant('(oa{sv})', (session, {})), GLib.VariantType.new('(h)'), Gio.DBusCallFlags.NONE, -1, None, None)
  fd = fds.get(reply.unpack()[0])
  try:
    pipeline = Gst.parse_launch('pipewiresrc fd=' + str(fd) + ' ' + target + ' num-buffers=5 ! videoconvert ! fakesink')
    pipeline.set_state(Gst.State.PLAYING)
    message = pipeline.get_bus().timed_pop_filtered(30 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    try:
      assert message is not None, 'Timed out receiving screen-sharing frames'
      if message.type == Gst.MessageType.ERROR:
        raise RuntimeError(message.parse_error())
      print('PASS: 5 real PipeWire screen-sharing frames received', flush=True)
    finally:
      pipeline.set_state(Gst.State.NULL)
  finally:
    os.close(fd)
finally:
  bus.call_sync(service, session, 'org.freedesktop.portal.Session', 'Close', None, None, Gio.DBusCallFlags.NONE, -1, None)

"""Disposable StatusNotifierItem/dbusmenu fixture for real PopupCard acceptance."""
from gi.repository import Gio,GLib
from pathlib import Path
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
xml='''<node>
<interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<property name="Category" type="s" access="read"/>
<property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/>
<property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/>
</interface>
<interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<property name="Version" type="u" access="read"/><property name="Status" type="s" access="read"/><property name="TextDirection" type="s" access="read"/>
</interface></node>'''
props={'Category':('s','ApplicationStatus'),'Id':('s','niri-qa-tray'),'Title':('s','Niri tray test'),'Status':('s','Active'),'IconName':('s','dialog-information'),'Menu':('o','/Menu'),'ItemIsMenu':('b',True),'Version':('u',3),'TextDirection':('s','ltr')}
item={'label':GLib.Variant('s','Niri test action'),'enabled':GLib.Variant('b',True),'visible':GLib.Variant('b',True)}
def method(conn,sender,path,interface,name,params,invocation):
  if name=='GetLayout':
    child=GLib.Variant('(ia{sv}av)',(1,item,[]))
    invocation.return_value(GLib.Variant('(u(ia{sv}av))',(1,(0,{'children-display':GLib.Variant('s','submenu')},[child]))))
  elif name=='GetGroupProperties':invocation.return_value(GLib.Variant('(a(ia{sv}))',([(1,item)],)))
  elif name=='AboutToShow':invocation.return_value(GLib.Variant('(b)',(False,)))
  else:
    if name=='Event':Path.home().joinpath('niri-tray-click.log').write_text(str(params.unpack()))
    invocation.return_value(None)
def getprop(conn,sender,path,interface,name):return GLib.Variant(*props[name]) if name in props else None
infos=Gio.DBusNodeInfo.new_for_xml(xml).interfaces
bus.register_object('/StatusNotifierItem',infos[0],method,getprop,None)
bus.register_object('/Menu',infos[1],method,getprop,None)
bus.call_sync('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','RegisterStatusNotifierItem',GLib.Variant('(s)',(bus.get_unique_name(),)),None,Gio.DBusCallFlags.NONE,5000,None)
print('Tray fixture registered',flush=True)
GLib.MainLoop().run()

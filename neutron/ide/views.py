import os
import time
import shutil
import codecs
import urllib

from django import http
from django.conf import settings
from django.template.response import TemplateResponse
import django.utils.simplejson as json
from django.contrib.auth.decorators import login_required
import django.contrib.auth.views as auth_views
from django.template.loader import render_to_string
from django.core.files.uploadedfile import SimpleUploadedFile
from django.views.static import serve

import ide.utils
import ide.settings
import ide.models
from ide.templatetags.ntags import hashstr

def login (request):
  return auth_views.login(request)
  
@login_required
def home (request):
  try:
    base_dir = request.user.preferences.basedir
    
  except:
    return TemplateResponse(request, 'ide/message.html', {'message': 'Please fill out a user preference.'})
    
  c = {
    'MODES': ide.settings.MODES,
    'THEMES': ide.settings.THEMES,
    'dir': base_dir,
    'did': 'file_browser',
    'd': base_dir,
  }
  
  return TemplateResponse(request, 'ide/home.html', c)
  
@login_required
def temp_file (request):
  fn = request.GET.get('name')
  
  mt = ide.util.mimetype(fn)
  f = SimpleUploadedFile(fn, request.raw_post_data, mt)
  
  t = ide.models.TempFile(file=f, user=request.user)
  t.save()
  
  return ide.utils.good_json(t.id)
  
@login_required
@ide.utils.valid_dir
def new (request):
  d = request.REQUEST.get('dir', '')
  new_type = request.REQUEST.get('new_type', '')
  name = request.REQUEST.get('name', '')
  
  fp = os.path.join(d, name)
  
  if new_type == 'file':
    if os.path.exists(fp):
      return ide.utils.bad_json('File Exists Already')
      
    fh = open(fp, 'w')
    fh.close()
    
  elif new_type == 'dir':
    if os.path.exists(fp):
      return ide.utils.bad_json('Directory Exists Already')
      
    os.mkdir(fp)
    
  elif new_type == 'url':
    uh = urllib.urlopen(name)
    
    if uh.info().has_key('Content-Disposition'):
      fn = uh.info()['Content-Disposition']
      
    else:
      fn = name.split('/')[-1]
      if fn == '':
        fn = time.strftime("%Y%m%d_%H%M%S.file", time.gmtime())
        
    fp = os.path.join(d, fn)
    if os.path.exists(fp):
      return ide.utils.bad_json('File Exists Already')
      
    fh = open(fp, 'wb')
    while 1:
      data = uh.read()
      fh.write(data)
      
      if not data:
        break
        
    fh.close()
    uh.close()
    
  else:
    tf = request.REQUEST.get('temp_file')
    tf = ide.models.TempFile.objects.get(id=tf, user=request.user)
    
    name = os.path.basename(tf.file.path)
    
    fp = os.path.join(d, name)
    if os.path.exists(fp):
      tf.file.delete()
      tf.delete()
      return ide.utils.bad_json('File Exists Already')
      
    shutil.move(tf.file.path, fp)
    tf.delete()
    
  return ide.utils.good_json()
  
@login_required
def filesave (request):
  ret = 'bad'
  error = None
  
  path = request.POST.get('path', '')
  contents = request.POST.get('contents', '')
    
  if path == '':
    error = 'Bad Request'
    
  else:
    if request.user.preferences.valid_path(path):
      try:
        fh = codecs.open(path, encoding='utf-8', mode='w')
        fh.write(contents)
        
      except:
        error = 'Error writing file to disk.'
        
      else:
        fh.close()
        ret = 'good'
        
    else:
      error = 'File Access Denied'
      
  return http.HttpResponse(json.dumps({'result': ret, 'error': error}), mimetype=settings.JSON_MIME)
    
@login_required
def fileget (request):
  try:
    base_dir = request.user.preferences.basedir
    
    f = request.POST.get('f', '')
    f = os.path.normpath(f)
    if not f.startswith(base_dir):
      raise http.Http404
      
    fh = open(f, 'rb')
    mode = None
    
    if ide.utils.istext(fh.read(512)):
      fh.seek(0)
      
      root, ext = os.path.splitext(f)
      if ext[1:].lower() in ide.settings.TEXT_EXTENSIONS.keys():
        mode = ide.settings.TEXT_EXTENSIONS[ext[1:].lower()]
        
      ret = {
        'fileType': 'text',
        'data': fh.read(),
        'path': f,
        'filename': os.path.basename(f),
        'mode': mode
      }
      
    else:
      ret = {'fileType': 'binary', }
      
    return http.HttpResponse(json.dumps(ret), mimetype=settings.JSON_MIME)
    
  except:
    import traceback
    traceback.print_exc()
    
@login_required
def filetree (request):
  r = ['<ul class="jqueryFileTree" style="display: none;">']
  show_hidden = False
  base_dir = request.user.preferences.basedir
  
  try:
    r = ['<ul class="jqueryFileTree" style="display: none;">']
    d = urllib.unquote(request.POST.get('dir', ''))
    
    if not d.startswith(base_dir):
      d = os.path.join(base_dir, d)
      
    d = os.path.normpath(d)
    if not d.startswith(base_dir):
      r.append('Invalid directory: %s' % str(d))
      
    fdlist = os.listdir(d)
    fdlist.sort()
    
    files = []
    dirs = []
    
    for f in fdlist:
      go = False
      if f.startswith('.'):
        if show_hidden:
          go = True
          
      else:
        go = True
        
      if go:
        ff = os.path.join(d,f)
        if os.path.isdir(ff):
          dirs.append((ff,f))
          
        else:
          e = os.path.splitext(f)[1][1:] # get .ext and remove dot
          files.append((e,ff,f))
          
    for d in dirs:
      did = hashstr(d[0])
      rm = render_to_string('ide/right_menu_dir.html', {'dir': d[0], 'did': did, 'd': os.path.basename(d[0])})
      r.append('<li class="directory collapsed" id="%s" title="%s">%s<a href="#" rel="%s/">%s</a></li>' % (did, d[0], rm, d[0], d[1]))
      
    for f in files:
      fid = hashstr(f[1])
      rm = render_to_string('ide/right_menu_file.html', {'f': f[2], 'fid': fid, 'file': f[1]})
      r.append('<li class="file ext_%s" id="%s">%s<a href="#" rel="%s">%s</a></li>' % (f[0], fid, rm, f[1], f[2]))
      
    r.append('</ul>')
    
  except Exception,e:
    r.append('Could not load directory: %s' % str(e))
    
  r.append('</ul>')
  return http.HttpResponse(''.join(r))
  
@login_required
@ide.utils.valid_file
def view_file (request):
  fp = request.REQUEST.get('file')
  fn = os.path.basename(fp)
  ret = serve(request, fp, document_root="/")
  ret['Content-Disposition'] = 'filename=%s' % fn
  return ret
  
@login_required
@ide.utils.valid_dir
def remove (request):
  path = request.REQUEST.get('dir')
  if os.path.isdir(path):
    shutil.rmtree(path)
    
  else:
    os.remove(path)
  
  d = os.path.dirname(path)
  if d == request.user.preferences.basedir:
    did = 'file_browser'
    
  else:
    did = hashstr(d)
    
  return ide.utils.good_json(did)
  
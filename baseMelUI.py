from pymel.core import PyNode

import pymel.versions as mayaVersion
import maya.cmds as cmd
import utils
import weakref
import filesystem

import wingdbstub

class MelUIError(Exception): pass


#this maps ui type strings to actual command objects - they're not always called the same
TYPE_NAMES_TO_CMDS = { u'staticText': cmd.text,
                       u'field': cmd.textField }

class BaseMelWidget(filesystem.trackableClassFactory( unicode )):
	'''
	This is a wrapper class for a mel widget to make it behave a little more like an object.  It
	inherits from str because thats essentially what a mel widget is - a name coupled with a mel
	command.  To interact with the widget the mel command is called with the UI name as the first arg.

	As a shortcut objects of this type are callable - the args taken depend on the specific command,
	and can be found in the mel docs.

	example:
	class AButtonClass(BaseMelWidget):
		WIDGET_CMD = cmd.button

	aButton = AButtonClass( parentName, label='hello' )
	aButton( edit=True, label='new label!' )
	'''

	#this should be set to the mel widget command used by this widget wrapped - ie cmd.button, or cmd.formLayout
	WIDGET_CMD = cmd.control

	#if not None, this is used to set the default width of the widget when created
	DEFAULT_WIDTH = None

	#default heights in 2011 aren't consistent - buttons are 24 pixels high by default (this is a minimum possible value too) while input fields are 20
	DEFAULT_HEIGHT = None if mayaVersion.current() < mayaVersion.v2011 else 24

	#this is the name of the kwarg used to set and get the "value" of the widget - most widgets use the "value" or "v" kwarg, but others have special names.  three cheers for mel!
	KWARG_VALUE_NAME = 'v'
	KWARG_VALUE_LONG_NAME = 'value'

	#this is the name of the "main" change command kwarg.  some widgets have multiple change callbacks that can be set, and they're not abstracted, but this is the name of the change cb name you want to be referenced by the setChangeCB method
	KWARG_CHANGE_CB_NAME = 'cc'

	#track instances so we can send them update messages -
	_INSTANCE_LIST = []

	@classmethod
	def Exists( cls, theControl ):
		if isinstance( theControl, BaseMelWidget ):
			return theControl.exists()

		return cmd.control( theControl, q=True, exists=True )

	def __new__( cls, parent, *a, **kw ):
		WIDGET_CMD = cls.WIDGET_CMD
		kw.pop( 'p', None )  #pop any parent specified in teh kw dict - set it explicitly to the parent specified
		if parent is not None:
			kw[ 'parent' ] = parent

		#set default sizes if applicable
		width = kw.pop( 'w', kw.pop( 'width', cls.DEFAULT_WIDTH ) )
		if isinstance( width, int ):
			kw[ 'width' ] = width

		height = kw.pop( 'h', kw.pop( 'height', cls.DEFAULT_HEIGHT ) )
		if isinstance( height, int ):
			kw[ 'height' ] = height

		#pop out the change callback if its been passed in with the kw dict, and run it through the setChangeCB method so it gets registered appropriately
		changeCB = kw.pop( cls.KWARG_CHANGE_CB_NAME, None )

		#this has the potential to be slow: it generates a unique name for the widget we're about to create, the benefit of doing this is that we're
		#guaranteed the widget LEAF name will be unique.  I'm assuming maya also does this, but I'm unsure.  if there are weird ui naming conflicts
		#it might be nessecary to uncomment this code
		baseName, n = WIDGET_CMD.__name__, 0
		uniqueName = '%s%d' % (baseName, n)
		while WIDGET_CMD( uniqueName, q=True, exists=True ):
			n += 1
			uniqueName = '%s%d' % (baseName, n)

		try:
			WIDGET_CMD( uniqueName, **kw )
		except:
			raise MelUIError( "Error trying to instantiate widget of type %s, with proposed name %s using the args %s" % (WIDGET_CMD, uniqueName, kw) )

		new = unicode.__new__( cls, uniqueName )
		new.parent = parent
		new._changeCB = changeCB
		cls._INSTANCE_LIST.append( new )

		return new
	def __init__( self, parent, *a, **kw ):
		changeCB = self._changeCB
		if changeCB:
			self.setChangeCB( changeCB )

		#make sure kw args passed to init are executed as edit commands (which should have been passed
		#to the cmd on creation, but we can't do that because we're inheriting from str, and we don't
		#want to force all subclasses to implement a __new__ method...
		self( edit=True, **kw )
	def __call__( self, *a, **kw ):
		return self.WIDGET_CMD( self, *a, **kw )
	def sendEvent( self, methodName, *methodArgs, **methodKwargs ):
		self.parent.processEvent( methodName,  *methodArgs, **methodKwargs )
	def processEvent( self, methodName, *methodArgs, **methodKwargs ):
		method = getattr( self, methodName, None )
		if callable( method ):
			method( *methodArgs, **methodKwargs )
		else:
			self.parent.processEvent( methodName, *methodArgs, **methodKwargs )
	def getVisibility( self ):
		return self( q=True, vis=True )
	def setVisibility( self, visibility=True ):
		if visibility:
			if hasattr( self, '_preSize' ):
				self.setSize( self._preSize )
		else:
			#cache the current size and set the size to as small as possible
			self._preSize = self.getSize()
			self.setSize( (1,1) )

		self( e=True, vis=visibility )
	def hide( self ):
		self.setVisibility( False )
	def show( self ):
		self.setVisibility( True )
	def setWidth( self, width ):
		self( e=True, width=width )
	def getWidth( self ):
		return self( q=True, width=True )
	def setHeight( self, height ):
		self( e=True, height=height )
	def getHeight( self ):
		return self( q=True, height=True )
	def setSize( self, widthHeight ):
		self( e=True, w=widthHeight[ 0 ], h=widthHeight[ 1 ] )
	def getSize( self ):
		w = self( q=True, w=True )
		h = self( q=True, h=True )
		return w, h
	def setValue( self, value, executeChangeCB=True ):
		try:
			kw = { 'e': True, self.KWARG_VALUE_NAME: value }
			self.WIDGET_CMD( self, **kw )
		except TypeError, x:
			print self.WIDGET_CMD
			raise

		if executeChangeCB:
			changeCB = self.getChangeCB()
			if callable( changeCB ):
				changeCB()
	def getValue( self ):
		kw = { 'q': True, self.KWARG_VALUE_NAME: True }
		return self.WIDGET_CMD( self, **kw )
	def getParent( self ):
		return self.parent
	def getTopParent( self ):
		parent = self.parent
		while True:
			try:
				parent = parent.parent
			except AttributeError: return parent
	def setChangeCB( self, cb ):
		kw = { 'e': True, self.KWARG_CHANGE_CB_NAME: cb }
		self.WIDGET_CMD( self, **kw )
		self._changeCB = cb
	def getChangeCB( self ):
		try:
			return self._changeCB
		except:
			return None
	def enable( self, state=True ):
		try: self( e=True, enable=state )
		except: pass
	def disable( self ):
		self.enable( False )
	def editable( self, state=True ):
		try: self( e=True, editable=state )
		except: pass
	def setEditable( self, state ):
		self.editable( state )
	def getEditable( self ):
		return bool( self( q=True, ed=True ) )
	def exists( self ):
		return cmd.control( self, ex=True )
	def delete( self ):
		cmd.deleteUI( self )
	@classmethod
	def FromStr( cls, theStr ):
		'''
		given a ui name, this will cast the string as a widget instance
		'''

		#assert cmd.control( theStr, exists=True )

		candidates = []
		uiTypeStr = cmd.objectTypeUI( theStr )
		uiCmd = TYPE_NAMES_TO_CMDS.get( uiTypeStr, getattr( cmd, uiTypeStr, None ) )

		#print cmd.objectTypeUI( theStr )  ##NOTE: the typestr isn't ALWAYS the same name as the function used to interact with said control, so this debug line can be useful for spewing object type names...

		if uiCmd is not None:
			for subCls in BaseMelWidget.GetSubclasses():
				if subCls.WIDGET_CMD is None: continue
				if subCls.WIDGET_CMD is uiCmd:
					candidates.append( subCls )

		theCls = cls
		if candidates:
			theCls = candidates[ 0 ]

		new = unicode.__new__( theCls, theStr )  #we don't want to run initialize on the object - just cast it appropriately
		cls._INSTANCE_LIST.append( new )

		return new
	@classmethod
	def IterInstances( cls ):
		existingInstList = []
		for inst in cls._INSTANCE_LIST:
			if not isinstance( inst, cls ):
				continue

			if cls.WIDGET_CMD( inst, q=True, exists=True ):
				existingInstList.append( inst )
				yield inst

		cls._INSTANCE_LIST = existingInstList


class MelLayout(BaseMelWidget):
	WIDGET_CMD = cmd.layout

	DEFAULT_WIDTH = None
	DEFAULT_HEIGHT = None

	def getChildren( self ):
		'''
		returns a list of all children UI items
		'''
		children = self( q=True, ca=True ) or []
		children = [ BaseMelWidget.FromStr( c ) for c in children ]

		return children
	def clear( self ):
		'''
		deletes all children from the layout
		'''
		for childUI in self.getChildren():
			cmd.deleteUI( childUI )


class MelForm(MelLayout): WIDGET_CMD = cmd.formLayout
class MelColumn(MelLayout): WIDGET_CMD = cmd.columnLayout
class MelRow(MelLayout): WIDGET_CMD = cmd.rowLayout
class MelScrollLayout(MelLayout):
	WIDGET_CMD = cmd.scrollLayout

	def __new__( cls, parent, *a, **kw ):
		kw.setdefault( 'childResizable', kw.pop( 'cr', True ) )

		return MelLayout.__new__( cls, parent, *a, **kw )


class MelTabLayout(MelLayout):
	WIDGET_CMD = cmd.tabLayout

	def __new__( cls, parent, *a, **kw ):
		kw.setdefault( 'childResizable', kw.pop( 'cr', True ) )

		return MelLayout.__new__( cls, parent, *a, **kw )
	def __init__( self, parent, *a, **kw ):
		kw.setdefault( 'selectCommand', kw.pop( 'sc', self.on_select ) )
		kw.setdefault( 'changeCommand', kw.pop( 'cc', self.on_change ) )
		kw.setdefault( 'preSelectCommand', kw.pop( 'psc', self.on_preSelect ) )
		kw.setdefault( 'doubleClickCommand', kw.pop( 'dcc', self.on_doubleClick ) )

		MelLayout.__init__( self, parent, *a, **kw )
	def numTabs( self ):
		return self( q=True, numberOfChildren=True )
	__len__ = numTabs
	def setLabel( self, idx, label ):
		self( e=True, tabLabelIndex=(idx+1, label) )
	def getLabel( self, idx ):
		self( q=True, tabLabelIndex=idx+1 )
	def getSelectedTab( self ):
		return self( q=True, selectTab=True )
	def on_select( self ):
		'''
		automatically hooked up if instantiated using this class - subclass to override
		'''
		pass
	def on_change( self ):
		'''
		automatically hooked up if instantiated using this class - subclass to override
		'''
		pass
	def on_preSelect( self ):
		'''
		automatically hooked up if instantiated using this class - subclass to override
		'''
		pass
	def on_doubleClick( self ):
		'''
		automatically hooked up if instantiated using this class - subclass to override
		'''
		pass


class MelPaneLayout(MelLayout):
	WIDGET_CMD = cmd.paneLayout

	PREF_OPTION_VAR = None

	POSSIBLE_CONFIGS = \
	                 CFG_SINGLE, CFG_HORIZ2, CFG_VERT2, CFG_HORIZ3, CFG_VERT3, CFG_TOP3, CFG_LEFT3, CFG_BOTTOM3, CFG_RIGHT3, CFG_HORIZ4, CFG_VERT4, CFG_TOP4, CFG_LEFT4, CFG_BOTTOM4, CFG_RIGHT4, CFG_QUAD = \
	                 "single", "horizontal2", "vertical2", "horizontal3", "vertical3", "top3", "left3", "bottom3", "right3", "horizontal4", "vertical4", "top4", "left4", "bottom4", "right4", "quad"

	CONFIG = CFG_VERT2

	KWARG_CHANGE_CB_NAME = 'separatorMovedCommand'

	def __new__( cls, parent, *a, **kw ):
		assert cls.CONFIG in cls.POSSIBLE_CONFIGS

		kw[ 'configuration' ] = cls.CONFIG
		kw.pop( 'cn', None )

		return super( MelPaneLayout, cls ).__new__( cls, parent, *a, **kw )
	def __init__( self, parent, *a, **kw ):
		kw.pop( 'smc', None )
		kw.setdefault( 'separatorMovedCommand', self.on_resize )

		super( MelPaneLayout, self ).__init__( parent, *a, **kw )

		if self.PREF_OPTION_VAR:
			if cmd.optionVar( ex=self.PREF_OPTION_VAR ):
				storedSize = cmd.optionVar( q=self.PREF_OPTION_VAR )
				for idx, size in enumerate( filesystem.iterBy( storedSize, 2 ) ):
					self.setPaneSize( idx, size )
	def __getitem__( self, idx ):
		idx += 1  #indices are 1-based...  fuuuuuuu alias!
		kw = { 'q': True, 'pane%d' % idx: True }

		return BaseMelWidget.FromStr( self( **kw ) )
	def __setitem__( self, idx, ui ):
		idx += 1  #indices are 1-based...  fuuuuuuu alias!
		return self( e=True, setPane=(ui, idx) )
	def getConfiguration( self ):
		return self( q=True, configuration=True )
	def setConfiguration( self, ui ):
		return self( e=True, configuration=ui )
	def getPaneUnderPointer( self ):
		return BaseMelWidget.FromStr( self( q=True, paneUnderPointer=True ) )
	def getPaneActive( self ):
		return BaseMelWidget.FromStr( self( q=True, activePane=True ) )
	def getPaneActiveIdx( self ):
		return self( q=True, activePaneIndex=True ) - 1  #indices are 1-based...
	def getPaneSize( self, idx ):
		idx += 1
		return self( q=True, paneSize=idx )
	def setPaneSize( self, idx, size ):
		idx += 1
		size = idx, size[0], size[1]

		return self( e=True, paneSize=size )
	def setPaneWidth( self, idx, size ):
		idx += 1
		curSize = self.getPaneSize( idx )
		return self( e=True, paneSize=(idx, curSize[0], size) )
	def setPaneHeight( self, idx, size ):
		idx += 1
		curSize = self.getPaneSize( idx )

		return self( e=True, paneSize=(idx, size, curSize[1]) )

	### EVENT HANDLERS ###
	def on_resize( self, *a ):
		if self.PREF_OPTION_VAR:
			size = self.getPaneSize( 0 )
			cmd.optionVar( clearArray=self.PREF_OPTION_VAR )
			for i in size:
				cmd.optionVar( iva=(self.PREF_OPTION_VAR, i) )


class MelLabel(BaseMelWidget):
	WIDGET_CMD = cmd.text
	KWARG_VALUE_NAME = 'l'
	KWARG_VALUE_LONG_NAME = 'label'

	#def __init__( self, parent, *a, **kw ):
		#if not( 'al' in kw or 'align' in kw ):
			#kw[ 'align' ] = '
	def bold( self, state=True ):
		self( e=True, font='boldLabelFont' if state else 'plainLabelFont' )
	getLabel = BaseMelWidget.getValue
	setLabel = BaseMelWidget.setValue


class MelButton(MelLabel):
	WIDGET_CMD = cmd.button
	KWARG_CHANGE_CB_NAME = 'c'

class MelCheckBox(BaseMelWidget):
	WIDGET_CMD = cmd.checkBox

	def __new__( cls, parent, *a, **kw ):
		#this craziness is so we can default the label to nothing instead of the widget's name...  dumb, dumb, dumb
		labelArgs = 'l', 'label'
		for f in kw.keys():
			if f == 'label':
				kw[ 'l' ] = kw.pop( 'label' )
				break

		kw.setdefault( 'l', '' )

		return BaseMelWidget.__new__( cls, parent, *a, **kw )


class MelIntField(BaseMelWidget):
	WIDGET_CMD = cmd.intField
	DEFAULT_WIDTH = 30

class MelFloatField(BaseMelWidget): WIDGET_CMD = cmd.floatField
class MelTextField(BaseMelWidget):
	WIDGET_CMD = cmd.textField
	DEFAULT_WIDTH = 150
	KWARG_VALUE_NAME = 'tx'
	KWARG_VALUE_LONG_NAME = 'text'

	def setValue( self, value, executeChangeCB=True ):
		if not isinstance( value, unicode ):
			value = unicode( value )

		BaseMelWidget.setValue( self, value, executeChangeCB )


class MelScrollField(MelTextField):
	WIDGET_CMD = cmd.scrollField


class MelNameField(MelTextField):
	WIDGET_CMD = cmd.nameField

	def getValue( self ):
		obj = self( q=True, o=True )
		if obj:
			return PyNode( obj )

		return None
	getObj = getValue
	def setValue( self, obj, executeChangeCB=True ):
		if not isinstance( obj, basestring ):
			obj = str( obj )

		self( e=True, o=obj )

		if executeChangeCB:
			changeCB = self.getChangeCB()
			if callable( changeCB ):
				changeCB()
	setObj = setValue
	def clear( self ):
		self.setValue( None )


class MelObjectSelector(MelForm):
	def __new__( cls, parent, label, obj=None, labelWidth=None ):
		return MelForm.__new__( cls, parent )
	def __init__( self, parent, label, obj=None, labelWidth=None ):
		self.UI_label = MelButton( self, l=label, c=self.on_setValue )
		self.UI_obj = MelNameField( self )

		if labelWidth is not None:
			self.UI_label.setWidth( labelWidth )

		if obj is not None:
			self.UI_obj.setValue( obj )

		self( e=True,
		      af=((self.UI_label, 'left', 0),
		          (self.UI_obj, 'right', 0)),
		      ac=((self.UI_obj, 'left', 0, self.UI_label)) )

		self.UI_menu = MelPopupMenu( self.UI_label )
		MelMenuItem( self.UI_menu, label='clear obj', c=self.on_clear )
	def getValue( self ):
		return self.UI_obj.getValue()
	def setValue( self, value, executeChangeCB=True ):
		return self.UI_obj.setValue( value, executeChangeCB )
	def clear( self ):
		self.UI_obj.clear()
	def getLabel( self ):
		return self.UI_label.getValue()
	def setLabel( self, label ):
		self.UI_label.setValue( label )

	### EVENT HANDLERS ###
	def on_setValue( self, *a ):
		sel = cmd.ls( sl=True )
		if sel:
			self.setValue( sel[ 0 ] )
	def on_clear( self, *a ):
		self.clear()


class MelTextScrollList(BaseMelWidget):
	WIDGET_CMD = cmd.textScrollList
	KWARG_CHANGE_CB_NAME = 'sc'

	ALLOW_MULTIPLE_TGTS = False

	def __init__( self, parent, *a, **kw ):
		if 'ams' not in kw and 'allowMultiSelection' not in kw:
			kw[ 'ams' ] = self.ALLOW_MULTIPLE_TGTS

		BaseMelWidget.__init__( self, parent, *a, **kw )
		self._appendCB = None
	def __getitem__( self, idx ):
		return self.getItems()[ idx ]
	def __contains__( self, value ):
		return value in self.getItems()
	def __len__( self ):
		return self( q=True, numberOfItems=True )
	def _runCB( self ):
		cb = self.getChangeCB()
		if callable( cb ):
			cb()
	def setItems( self, items ):
		self.clear()
		for i in items:
			self.append( i )
	def getItems( self ):
		return self( q=True, ai=True )
	def setAppendCB( self, cb ):
		self._appendCB = cb
	def getSelectedItems( self ):
		return self( q=True, si=True ) or []
	def getSelectedIdxs( self ):
		return [ idx-1 for idx in self( q=True, sii=True ) or [] ]
	def selectByIdx( self, idx, executeChangeCB=False ):
		self( e=True, selectIndexedItem=idx+1 )  #indices are 1-based in mel land - fuuuuuuu alias!!!
		if executeChangeCB:
			self._runCB()
	def attemptToSelect( self, idx, executeChangeCB=False ):
		'''
		attempts to select the item at index idx - if the specific index doesn't exist,
		it tries to select the closest item to the given index
		'''
		if len( self ) == 0:
			if executeChangeCB: self._runCB()
			return

		if idx >= len( self ):
			idx = len( self ) - 1  #set to the end most item

		if idx < 0:
			idx = 0

		self.selectByIdx( idx, executeChangeCB )
	def selectByValue( self, value, executeChangeCB=False ):
		self( e=True, selectItem=value )
		if executeChangeCB:
			cb = self.getChangeCB()
			if callable( cb ):
				cb()
	def append( self, item ):
		self( e=True, append=item )
	def appendItems( self, items ):
		for i in items: self.append( i )
	def removeByIdx( self, idx ):
		self( e=True, removeIndexedItem=idx+1 )
	def removeByValue( self, value ):
		self( e=True, removeItem=value )
	def removeSelectedItems( self ):
		for idx in self.getSelectedIdxs():
			self.removeByIdx( idx )
	def clear( self ):
		self( e=True, ra=True )
	def clearSelection( self ):
		self( e=True, deselectAll=True )
	def moveSelectedItemsUp( self, count=1 ):
		'''
		moves selected items "up" <count> units
		'''
		selIdxs = self.getSelectedIdxs()
		selIdxs.sort()

		count = min( count, selIdxs[ 0 ] )  #we can't move more units up than the smallest selected index
		if selIdxs[ 0 ] > 0:
			items = self.getItems()
			itemsToMove = [ items[ idx ] for idx in selIdxs ]
			for idx in reversed( selIdxs ):
				item = items.pop( idx )
				items.insert( idx-count, item )

			self.setItems( items )

			#re-setup selection
			self.clearSelection()
			for idx in selIdxs:
				self.selectByIdx( idx-count, False )
	def moveSelectedItemsDown( self, count=1 ):
		'''
		moves selected items "down" <count> units
		'''
		selIdxs = self.getSelectedIdxs()
		selIdxs.sort()

		items = self.getItems()
		maxIdx = len( items )-1

		count = min( count, maxIdx - selIdxs[-1] )  #we can't move more units down than the largest selected index
		if selIdxs[ -1 ] < maxIdx:
			itemsToMove = [ items[ idx ] for idx in selIdxs ]
			for idx in reversed( selIdxs ):
				item = items.pop( idx )
				items.insert( idx+count, item )

			self.setItems( items )

			#re-setup selection
			self.clearSelection()
			for idx in selIdxs:
				self.selectByIdx( idx+count, False )


class MelObjectScrollList(MelTextScrollList):
	'''
	this class will actually return and store a python object and display it as a string item
	in the list.  it also lets you set selection by passing either a string, index or actual
	python object
	'''

	#if true the objects are displayed without their namespaces
	DISPLAY_NAMESPACES = False

	def __init__( self, parent, *a, **kw ):
		MelTextScrollList.__init__( self, parent, *a, **kw )
		self._items = []
	def itemAsStr( self, item ):
		if self.DISPLAY_NAMESPACES:
			return str( item )
		else:
			withoutNamespace = str( item ).split( ':' )[ -1 ]
			withoutPaths = withoutNamespace.split( '|' )[ -1 ]

			return withoutPaths
	def getItems( self ):
		return self._items
	def getSelectedItems( self ):
		selectedIdxs = self.getSelectedIdxs()
		return [ self._items[ idx ] for idx in selectedIdxs ]
	def selectByValue( self, value, executeChangeCB=False ):
		if value in self._items:
			idx = self._items.index( value ) + 1  #mel indices are 1-based...
			self( e=True, sii=idx )
		else:
			valueStr = self.itemAsStr( value )
			for idx, item in enumerate( self._items ):
				if self.itemAsStr( item ) == valueStr:
					self( e=True, sii=idx+1 )  #mel indices are 1-based...

		if executeChangeCB:
			cb = self.getChangeCB()
			if callable( cb ):
				cb()
	def append( self, item ):
		self._items.append( item )
		self( e=True, append=self.itemAsStr( item ) )
		if callable( self._appendCB ):
			self._appendCB( item )
	def removeByIdx( self, idx ):
		self._items.pop( idx )
		self( e=True, removeIndexedItem=idx+1 )
	def removeByValue( self, value ):
		if value in self._items:
			idx = self._items.index( value )
			self._items.pop( idx )
			self( e=True, rii=idx+1 )  #mel indices are 1-based...
		else:
			valueStr = self.itemAsStr( value )
			for idx, item in enumerate( self._items ):
				if self.itemAsStr( item ) == valueStr:
					self._items.pop( idx )
					self( e=True, rii=idx+1 )  #mel indices are 1-based...
	def clear( self ):
		self._items = []
		self( e=True, ra=True )
	def update( self, maintainSelection=True ):
		selIdxs = self.getSelectedIdxs()

		#remove all items from the list
		self( e=True, ra=True )

		#now re-generate their string representations
		for item in self._items:
			self( e=True, append=self.itemAsStr( item ) )

		if maintainSelection:
			for idx in selIdxs:
				self.selectByIdx( idx, False )


class _MelBaseMenu(BaseMelWidget):
	DYNAMIC = False

	KWARG_VALUE_NAME = 'l'
	KWARG_VALUE_LONG_NAME = 'label'

	KWARG_CHANGE_CB_NAME = 'pmc'

	DEFAULT_WIDTH = None
	DEFAULT_HEIGHT = None

	def __init__( self, parent, *a, **kw ):
		super( _MelBaseMenu, self ).__init__( parent, *a, **kw )
		if self.DYNAMIC:
			if 'pmc' not in kw and 'postMenuCommand' not in kw:  #make sure there isn't a pmc passed in
				self( e=True, pmc=self._build )
	def __len__( self ):
		return self( q=True, numberOfItems=True )
	def _build( self, menu, menuParent ):
		'''
		converts the menu and menuParent args into proper MelXXX instance
		'''
		menu = BaseMelWidget.FromStr( menu )
		menuParent = BaseMelWidget.FromStr( menuParent )

		self.build( menu, menuParent )
	def build( self, menu, menuParent ):
		pass
	def getMenuItems( self ):
		itemNames = self( q=True, itemArray=True ) or []
		return [ MelMenuItem.FromStr( itemName ) for itemName in itemNames ]
	def getItems( self ):
		return [ menuItem.getValue() for menuItem in self.getMenuItems() ]
	def append( self, strToAppend ):
		return MelMenuItem( self, label=strToAppend )
	def clear( self ):
		for menuItem in self.getMenuItems():
			cmd.deleteUI( menuItem )


class MelMenu(_MelBaseMenu):
	WIDGET_CMD = cmd.menu
	DYNAMIC = True

	def __new__( self, *a, **kw ):
		return _MelBaseMenu.__new__( self, None, *a, **kw )
	def __init__( self, *a, **kw ):
		super( _MelBaseMenu, self ).__init__( None, *a, **kw )
		if self.DYNAMIC:
			if 'pmc' not in kw and 'postMenuCommand' not in kw:  #make sure there isn't a pmc passed in
				self( e=True, pmc=self._build )


class MelOptionMenu(_MelBaseMenu):
	WIDGET_CMD = cmd.optionMenu

	KWARG_VALUE_NAME = 'v'
	KWARG_VALUE_LONG_NAME = 'value'
	KWARG_CHANGE_CB_NAME = 'cc'

	DYNAMIC = False

	def __getitem__( self, idx ):
		return self.getItems()[ idx ]
	def __setitem__( self, idx, value ):
		menuItems = self.getMenuItems()
		menuItems[ idx ].setValue( value )
	def getMenuItems( self ):
		itemNames = self( q=True, itemListLong=True ) or []
		return [ MelMenuItem.FromStr( itemName ) for itemName in itemNames ]
	def selectByIdx( self, idx, executeChangeCB=True ):
		self( e=True, select=idx+1 )  #indices are 1-based in mel land - fuuuuuuu alias!!!
		if executeChangeCB:
			cb = self.getChangeCB()
			if callable( cb ):
				cb()
	def selectByValue( self, value, executeChangeCB=True ):
		idx = self.getItems().index( value )
		self.selectByIdx( idx, executeChangeCB )
	def setValue( self, value, executeChangeCB=True ):
		self.selectByValue( value, executeChangeCB )


class MelPopupMenu(_MelBaseMenu):
	WIDGET_CMD = cmd.popupMenu
	DYNAMIC = True

	def clear( self ):
		self( e=True, dai=True )  #clear the menu


class MelMenuItem(BaseMelWidget):
	WIDGET_CMD = cmd.menuItem

	KWARG_VALUE_NAME = 'l'
	KWARG_VALUE_LONG_NAME = 'label'

	DEFAULT_WIDTH = None
	DEFAULT_HEIGHT = None


class MelMenuItemDiv(MelMenuItem):
	def __new__( cls, parent, *a, **kw ):
		kw[ 'divider' ] = True
		super( MelMenuItemDiv, cls ).__new__( cls, parent, *a, **kw )


class MelProgressWindow(BaseMelWidget):
	WIDGET_CMD = cmd.progressWindow

	KWARG_VALUE_NAME = 'pr'
	KWARG_VALUE_LONG_NAME = 'progress'

	def __new__( cls, title, message, increment ):
		return unicode.__new__( cls, 'aProgressWindow' )
	def __init__( self, title, message='', increment=0 ):
		self.progress = 0
		self._inc = increment

		self.WIDGET_CMD( t=title, status=message, progress=0, isInterruptable=True )
	def __del__( self ):
		self.close()
	def next( self ):
		self.progress += self._inc
		self.WIDGET_CMD( e=True, pr=self.progress )
	def getMessage( self ):
		return self.WIDGET_CMD( q=True, status=True )
	def setMessage( self, message ):
		self.WIDGET_CMD( e=True, status=message )
	def isCancelled( self ):
		return self.WIDGET_CMD( q=True, ic=True )
	def close( self ):
		self.WIDGET_CMD( e=True, ep=True )


UI_FOR_PY_TYPES = { bool: MelCheckBox,
                    int: MelIntField,
                    float: MelFloatField,
                    basestring: MelTextField,
                    list: MelTextScrollList,
                    tuple: MelTextScrollList }

def buildUIForObject( obj, parent, typeMapping=None ):
	'''
	'''
	if typeMapping is None:
		typeMapping = UI_FOR_PY_TYPES

	objType = obj if type( obj ) is type else type( obj )

	#first see if there is an exact type match in the dict
	buildClass = None
	try: buildClass = typeMapping[ objType ]
	except KeyError:
		#if not, see if there is an inheritance match
		for aType, aBuildClass in typeMapping.iteritems():
			if issubclass( objType, aType ):
				buildClass = aBuildClass
				break

	if buildClass is None:
		raise MelUIError( "there is no build class defined for object's of type %s (%s)" % (type( obj ), obj) )

	ui = buildClass( parent )
	ui.setValue( obj )

	return ui


class BaseMelWindow(unicode):
	'''
	This is a wrapper class for a mel window to make it behave a little more like an object.  It
	inherits from str because thats essentially what a mel widget is.

	Objects of this class are callable.  Calling an object is basically the same as passing the given
	args to the cmd.window maya command:

	aWindow = BaseMelWindow()
	aWindow( q=True, exists=True )

	is the same as doing:
	aWindow = cmd.window()
	cmd.window( aWindow, q=True, exists=True )
	'''
	WINDOW_NAME = 'unnamed_window'
	WINDOW_TITLE = 'Unnamed Tool'

	DEFAULT_SIZE = None
	DEFAULT_MENU = 'File'
	DEFAULT_MENU_IS_HELP = False

	FORCE_DEFAULT_SIZE = False

	@classmethod
	def Exists( cls ):
		'''
		returns whether there is an instance of this class already open
		'''
		return cmd.window( cls.WINDOW_NAME, ex=True )
	@classmethod
	def Close( cls ):
		'''
		closes the window (if it exists)
		'''
		if cls.Exists():
			cmd.deleteUI( cls.WINDOW_NAME )

	def __new__( cls, *a, **kw ):
		kw.setdefault( 'title', cls.WINDOW_TITLE )
		kw.setdefault( 'widthHeight', cls.DEFAULT_SIZE )
		kw.setdefault( 'menuBar', True )

		if cmd.window( cls.WINDOW_NAME, ex=True ):
			cmd.deleteUI( cls.WINDOW_NAME )

		new = unicode.__new__( cls, cmd.window( cls.WINDOW_NAME, **kw ) )
		if cls.DEFAULT_MENU is not None:
			cmd.menu( l=cls.DEFAULT_MENU, helpMenu=cls.DEFAULT_MENU_IS_HELP )

		return new
	def __call__( self, *a, **kw ):
		return cmd.window( self, *a, **kw )
	def setTitle( self, newTitle ):
		cmd.window( self.WINDOW_NAME, e=True, title=newTitle )
	def getMenus( self ):
		menus = self( q=True, menuArray=True ) or []
		return [ MelMenu.FromStr( m ) for m in menus ]
	def getMenu( self, menuName, createIfNotFound=True ):
		'''
		returns the UI name for the menu with the given name
		'''
		for m in self.getMenus():
			if m.getValue() == menuName:
				return m

		if createIfNotFound:
			return MelMenu( l=menuName, helpMenu=menuName.lower()=='help' )
	def show( self, state=True ):
		if state:
			cmd.showWindow( self )
		else:
			self( e=True, visible=False )

		if self.FORCE_DEFAULT_SIZE:
			self( e=True, widthHeight=self.DEFAULT_SIZE )
	def layout( self ):
		'''
		forces the window to re calc layouts for children
		'''
		curWidth = self( q=True, width=True )
		self( e=True, width=curWidth+1 )
		self( e=True, width=curWidth )
	def processEvent( self, methodName, *methodArgs, **methodKwargs ):
		method = getattr( self, methodName, None )
		if callable( method ):
			method( *methodArgs, **methodKwargs )


#end
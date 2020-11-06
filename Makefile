packer = tar
pack = $(packer) caf
arcx = .tar.xz
todo = TODO
docs = Changelog LICENSE README.md $(todo)
basename = orgmode
srcversion = orgmodeparser
version = $(shell python3 -c 'from $(srcversion) import VERSION; print(VERSION)')
branch = $(shell git symbolic-ref --short HEAD)
arcname = $(basename)$(arcx)
srcarcname = $(basename)-$(branch)-src$(arcx)
srcs = orgmodeparser.py
backupdir = ~/shareddocs/pgm/python/

archive:
	$(pack) $(srcarcname) *.py *.org Makefile *.geany $(docs)
backup:
	make archive
	mv $(srcarcname) $(backupdir)
update:
	$(packer) x -y $(backupdir)$(srcarcname)
commit:
	git commit -a -uno -m "$(version)"
docview:
	$(eval docname = README.htm)
	@echo "<html><head><meta charset="utf-8"><title>$(title_version) README</title></head><body>" >$(docname)
	markdown_py README.md >>$(docname)
	@echo "</body></html>" >>$(docname)
	x-www-browser $(docname)
	#rm $(docname)
show-branch:
	@echo "$(branch)"
todo:
	pytodo.py $(srcs) >$(todo)
edit-sample:
	emacs --no-desktop -nw sample.org

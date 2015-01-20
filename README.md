The Rolling Pin
===============

<img src="https://upload.wikimedia.org/wikipedia/commons/1/19/Work_dough.jpg" width="280" height="210" align="right" alt="">

A tool for rolling changes out to servers.

To roll stuff out, select a group of hosts to affect:

* a master list of hosts is collected by the "host source" which is pluggable.
* aliased hostname glob expressions specify which hosts to pay attention to (`-h`)
* the list may be truncated by starting after (`--startat`) or stopping before
  (`--stopbefore`) specified hosts

And what commands you'd like to run:

* components to deploy get built on a central build server then deployed to
  individual hosts (`-d`)
* restart services (`-r`)
* arbitrary other commands may be specified as long as the remote end knows how
  to execute them (`-c`)

The rollout will then begin:

* rollouts are executed by the "transport" which is pluggable and defaults to ssh.
* hosts are "enqueued" one at a time with an optional delay between them
  (`--sleeptime`)
* multiple hosts can be worked on in parallel (`--parallel`)
* after a number of hosts have completed their work, the rollout can pause to
  allow [sanity checking][1] before continuing on (`--pauseafter`)

If configured, graphite will be sent a metric of the form
`events.deploy.{component}` for each component deployed.

The rolling pin also features integration with [Harold][2].

See [example.ini](example.ini) for configuration instructions.


[1]: http://i.imgur.com/66Nr9Wo.jpg
[2]: https://github.com/spladug/harold

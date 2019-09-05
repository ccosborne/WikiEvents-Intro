#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May 15 11:06:53 2018

Condensed version of WikiEvents code.

Generate one hop Wikipedia article network around target article(s).

Do this in several languages and save the output as both an edgelist csv and a graphml.

@author: Patrick Gildersleve, patrick.gildersleve@oii.ox.ac.uk

Updates:
    22/06/2018 - Fixed bug where core articles were removed from network in some languages
"""

import pandas as pd
import wikipedia as wiki
import networkx as nx
import requests
import datetime

def query(request): # For basic wiki api queries
    request['action'] = 'query'
    request['format'] = 'json'
    lastContinue = {}
    while True:
        # Clone original request
        req = request.copy()
        # Modify it with the values returned in the 'continue' section of the last result.
        req.update(lastContinue)
        # Call API
        result = requests.get('https://%s.wikipedia.org/w/api.php' %lang, params=req).json()
        if 'error' in result:
            print('erroorrrr')
            print(result['error'])
            #raise Error(result['error'])
        if 'warnings' in result:
            print(result['warnings'])
        if 'query' in result:
            yield result['query']
        if 'continue' not in result:
            break
        lastContinue = result['continue']
#        print(result)


def chunks(l, n): # breaks a list into several of length 50
# For item i in a range that is a length of l,
    for i in range(0, len(l), n):
        # Create an index range for l of n items:
        yield l[i:i+n]

class event:

    def __init__(self, corenames, initialise = True):
        self.description = ''

        self.core_article_names = corenames
        self.core_articles = {}
        self.neighbours = pd.DataFrame(columns = ['title', 'pageid'])
        self.redlinks = set()
        self.all_articles = pd.DataFrame(columns = ['title', 'pageid'])
        self.titlemap = {}
        self.idmap = {}

        self.core_edgelist = pd.DataFrame(columns = ['source', 'target'])
        self.all_edgelist = pd.DataFrame(columns = ['source', 'target'])

        self.graph = nx.DiGraph

        if initialise == True:
            self.core_ids()
            if self.core_ids != 'error':
                self.get_neighbours()
                self.get_linksfromneighbours()
                self.get_graphs()

    def fix_redir(self, articles):
        print('Fixing redirects')
        targets = set(articles)

        tar_chunks = list(chunks(list(targets), 50))

        mapping = {}
        rcount = 0
        for n, i in enumerate(tar_chunks):
            print('Fixing redirects', round(100*n/len(tar_chunks), 2), '%')
            istr = '|'.join(i)
            params = {'titles':istr,'redirects':''}
            dat  = list(query(params))
            for j in dat:
                for k, v in j['pages'].items():
                        self.idmap[v['title']] = k

                try:
                    for k in j['redirects']:
                        m = list(k.values())
                        mapping[m[0]] = m[1]
                        rcount+=1


                except KeyError:
                    pass

        # Apply mapping to self to fix second order redirects
        #print('Consolidating mapping')
        n=0
        self.titlemap = mapping.copy()
        for k, v in mapping.items():
            print('Consolidating mapping', round(100*n/len(mapping), 2), '%')
            n+=1
            for i in mapping.keys():
                if i == v:
                    self.titlemap[k] = mapping[i]

    def core_ids(self): #get page ID of core articles
        wiki.set_lang(lang)

        try:
            print('Page ID is: {}'.format(wiki.WikipediaPage(title=self.core_article_names).pageid))
            #print(self.core_articles.items())
            print('Good - there are pages to link to')
            WikiError= False

        except wiki.exceptions.PageError:
            print('No pageid. Page is most likely a stub article')
            WikiError=True

        except AssertionError:
            print('Assertion Error')
            WikiError = True

        except KeyError:
            print('Key Error')
            WikiError = True

        if WikiError == True:
            self.core_ids = 'Error'
        else:
            self.core_articles = {i:str(int(wiki.WikipediaPage(title=i).pageid)) for i in self.core_article_names}
            for k, v in self.core_articles.items():
                self.all_articles = self.all_articles.append({'title':k, 'pageid':v}, ignore_index = True)

    def get_neighbours(self): # get neighbours of core articles
        in_neighbours = pd.DataFrame(columns = ['title', 'pageid']) # df of neighbours that link to core
        out_neighbours = pd.DataFrame(columns = ['title', 'pageid']) # df of neighbours that core links to
        out_titles = set()
        print('Article' in list(self.all_articles['title']))

        for page, pageid in self.core_articles.items():
            print('Getting links for %s. PageID %s' %(page, pageid))
            in_params = {'list':'backlinks', 'bltitle':page, 'blnamespace':'0', 'bllimit':250, 'blfilterredir':'nonredirects', 'blredirect':'True'} # redirects x 2
            in_dat = list(query(in_params)) # Pages that link to core

            out_params = {'titles':page, 'prop':'links', 'pllimit':'max', 'plnamespace':'0'} # redirects
            out_dat = list(query(out_params)) # Pages that core links to

            if page not in self.redlinks: # if redlink not-page, this is not quite correct.
                i_in_neighbours = pd.DataFrame(columns = ['title', 'pageid'])
                i_out_neighbours = []
                for n in in_dat:
                    for j in n['backlinks']:
                        if 'redirlinks' in j.keys(): # check for pages that link via redirect
                            for k in j['redirlinks']:
                                i_in_neighbours = i_in_neighbours.append({'title':k['title'], 'pageid':k['pageid']}, ignore_index=True)
                        else: # add pages that link normally
                            i_in_neighbours = i_in_neighbours.append({'title':j['title'], 'pageid':j['pageid']}, ignore_index=True)

                for n in out_dat:
                    i_out_neighbours.extend([j['title'] for j in n['pages'][pageid]['links']])
                in_neighbours = pd.concat([in_neighbours, i_in_neighbours], ignore_index = True) # add page
                out_titles |= set(i_out_neighbours)

            print('Creating core edgelist')
            # Add out neighbours
            el = pd.DataFrame({'source':[page for x in i_out_neighbours], 'target':i_out_neighbours})
            self.core_edgelist = self.core_edgelist.append(el, ignore_index=True)

            # Add in neighbours
            el = pd.DataFrame({'source':i_in_neighbours['title'], 'target':[page for x in i_in_neighbours['title']]})
            self.core_edgelist = self.core_edgelist.append(el, ignore_index=True)

        out_t = list(out_titles)

        # Join in/out neighbours into all articles df
        all_neigh = pd.concat([in_neighbours['title'], pd.Series(out_t)], ignore_index = True)
        self.all_articles = self.all_articles.append([{'title':x, 'pageid':0} for x in all_neigh], ignore_index = True)
        self.all_articles['title'] = self.all_articles['title'].append(all_neigh, ignore_index = True)

        self.all_articles.drop_duplicates(inplace = True)
        self.all_articles.reset_index(drop=True, inplace=True)

        self.fix_redir(self.all_articles['title'])
        self.all_articles['title'] = self.all_articles['title'].map(lambda x: self.titlemap.get(x,x))
        self.all_articles['pageid'] = self.all_articles['title'].map(self.idmap)
        self.all_articles.drop_duplicates(inplace = True)
        self.all_articles.reset_index(drop=True, inplace=True)

        self.core_edgelist = self.core_edgelist.applymap(lambda x: self.titlemap.get(x,x))

        print('creating combined list')
        self.core_edgelist.drop_duplicates(inplace = True) # remove duplicates
        self.core_edgelist = self.core_edgelist[~self.core_edgelist['source'].isin(self.redlinks)] #remove redlinks
        self.core_edgelist = self.core_edgelist[~self.core_edgelist['target'].isin(self.redlinks)] #remove redlinks

    def get_linksfromneighbours(self): # get all links in network
        # Create edge list for all
        global all_el
        all_el = pd.DataFrame(columns = ['source', 'target'])

        title_lists = list(chunks(list(self.all_articles['title']), 50))
        print('Getting links from all %d articles' %len(self.all_articles))

        for n, l in enumerate(title_lists):
            print('Getting links ', round(100*n/len(title_lists), 3), '%')
            ts = '|'.join(l)
            params = {'titles':ts, 'prop':'links', 'pllimit':'max', 'plnamespace':'0', 'redirects':''} # redirects
            dat = list(query(params))

            for i in dat:
                for k, v in i['pages'].items():
                    if 'links' in v.keys():
                        # commented code could go here?
                        el = pd.DataFrame({'source':v['title'], 'target':[x['title'] for x in v['links']]})
                        all_el = all_el.append(el, ignore_index=True)

        all_el.drop_duplicates(inplace = True)
        print(len(all_el))


        self.fix_redir(set(all_el['source']) | set(all_el['target']) | set(self.all_articles['title']))

        # Apply mapping to edgelist and article list
        print('Replacing values')
        mall_el = all_el.applymap(lambda x: self.titlemap.get(x,x))
        mall_el.drop_duplicates(inplace = True)
        self.all_articles['title'] = self.all_articles['title'].map(lambda x: self.titlemap.get(x,x))

        # Only keep edges where both nodes in article list
        print(len(mall_el))
        mall_el = mall_el[mall_el['target'].isin(self.all_articles['title'])]
        print(len(mall_el))
        self.all_edgelist = mall_el[mall_el['source'].isin(self.all_articles['title'])]
        self.all_edgelist.reset_index(inplace=True, drop=True)
        print(len(self.all_edgelist))

    def get_graphs(self):
        print('Generating graphs')
        self.graph = nx.from_pandas_edgelist(self.all_edgelist, 'source', 'target', create_using = nx.DiGraph())

# lang code and corresponding article title(s) in a list (add as necessary)
t_dict = {'en':['World War II'],
          'de':['Zweiter Weltkrieg']}

date = datetime.datetime.now().strftime("%d-%m-%Y_%H%M") # get current datetime
path = '' # Set path here, folder must already exist

for k, v in t_dict.items(): #iterate through languages
    print(k, v)
    lang = k # set wiki language
    test_event = event(v) # generate 1 hop network around target article(s)
    test_event.all_edgelist.to_csv('%s%s_%s.csv' %(path, k, date), index=False) # save edgelist to csv
    nx.write_graphml(test_event.graph, '%s%s_%s.graphml' %(path, k, date)) # save graph to graphml
    

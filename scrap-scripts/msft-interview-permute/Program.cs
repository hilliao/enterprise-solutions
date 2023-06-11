﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Permute0
{
    /*
     )      Given a string, write a method to return all permutations of that string (i.e. same length permutations)

Ex: 
               Abc > abc, acb, bac, bca, cab, cba
     */

    class Program
    {
        //solution: Look at the debugger output window for the permuted string test results
        static void Main(string[] args)
        {
            List<char> sample = new List<char> {'a', 'b', 'c'};
            IEnumerable<IEnumerable<char>> permuted = GetPermutations(sample, sample.Count);
            foreach (IEnumerable<char> p in permuted)
            {
                //each p is a permuted result
                foreach (char c in p)
                {
                    System.Diagnostics.Debug.Write(c);
                }
                System.Diagnostics.Debug.WriteLine(string.Empty);
            }
            System.Diagnostics.Debugger.Break();
        }

        static IEnumerable<IEnumerable<T>> GetPermutations<T>(IEnumerable<T> list, int length)
        {
            if (length == 1)
            {
                var partial = list.Select(a => new List<T> { a });
                return partial;
            }
            else
            {
                //
                IEnumerable<IEnumerable<T>> perm = GetPermutations(list, length - 1);
                IEnumerable<IEnumerable<T>> r = perm.SelectMany(
                    x => list.Where(y => !x.Contains(y)),
                    (x, c) => x.Concat(new T[] { c }));
                return r;
            }
        }
    }
}